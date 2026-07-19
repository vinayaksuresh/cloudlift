import os

from cloudlift.config.logging import log, log_bold
from cloudlift.deployment.deployer import read_config
from cloudlift.exceptions import UnrecoverableException
from cloudlift.providers.gcp.artifact_registry import ArtifactRegistryClient
from cloudlift.providers.gcp.clients import GcpClients
from cloudlift.providers.gcp.config import GcpEnvironmentConfig
from cloudlift.providers.gcp.gke import GkeDeployer
from cloudlift.providers.gcp.secrets import SecretManagerConfigStore


class GcpProvider(object):
    name = "gcp"

    def __init__(self, clients_factory=None):
        self.clients_factory = clients_factory or GcpClients.from_adc

    def create_environment(self, environment, **kwargs):
        config = GcpEnvironmentConfig.load_or_create(
            environment,
            path=kwargs.get("config_path"),
            project_id=kwargs.get("project_id"),
            location=kwargs.get("location"),
            cluster_name=kwargs.get("cluster_name"),
            namespace=kwargs.get("namespace"),
            artifact_registry_repository=kwargs.get("artifact_registry_repository"),
            service_account=kwargs.get("service_account"),
        )
        clients = self.clients_factory(config)
        clients.ensure_namespace_exists()
        log_bold("Registered GCP GKE environment {} using namespace {}".format(
            environment,
            config.namespace,
        ))
        return config

    def update_environment(self, environment, **kwargs):
        return self.create_environment(environment, **kwargs)

    def create_service(self, name, environment, **kwargs):
        return self._apply_service(name, environment, **kwargs)

    def update_service(self, name, environment, **kwargs):
        return self._apply_service(name, environment, **kwargs)

    def deploy_service(self, name, environment, version=None, **kwargs):
        config = GcpEnvironmentConfig.load(environment, kwargs.get("config_path"))
        clients = self.clients_factory(config)
        image = ArtifactRegistryClient(config).image_uri(name, version or "latest")
        log_bold("Deploying {} to GKE with image {}".format(name, image))
        return GkeDeployer(config, clients.apps_v1_api, clients.core_v1_api).deploy_image(name, image)

    def create_task_definition(self, *_args, **_kwargs):
        raise UnrecoverableException(
            "GCP provider does not support ECS task definitions. Use create_service or deploy_service for GKE."
        )

    def update_task_definition(self, *_args, **_kwargs):
        raise UnrecoverableException(
            "GCP provider does not support ECS task definitions. Use update_service or deploy_service for GKE."
        )

    def upload_image(self, name, environment="", local_tag=None, additional_tags=None, **kwargs):
        if not environment:
            raise UnrecoverableException("--environment is required when uploading images with --provider gcp")
        config = GcpEnvironmentConfig.load(environment, kwargs.get("config_path"))
        return ArtifactRegistryClient(config).tag_and_push(name, local_tag, additional_tags)

    def get_version(self, name, environment, short=False, **kwargs):
        config = GcpEnvironmentConfig.load(environment, kwargs.get("config_path"))
        clients = self.clients_factory(config)
        deployment = clients.apps_v1_api.read_namespaced_deployment(name, config.namespace)
        container = deployment.spec.template.spec.containers[0]
        image = container.image
        version = image.rsplit(":", 1)[-1] if ":" in image else image
        if short:
            print(version)
        else:
            log("Currently deployed version: " + version)
        return version

    def _apply_service(self, name, environment, **kwargs):
        config = GcpEnvironmentConfig.load(environment, kwargs.get("config_path"))
        clients = self.clients_factory(config)
        env_keys = self._env_sample_keys(kwargs.get("env_sample_file") or "./env.sample")
        env_refs = SecretManagerConfigStore(
            config,
            clients.secret_manager_client,
        ).kubernetes_env_refs(name, env_keys)
        image = kwargs.get("image") or ArtifactRegistryClient(config).image_uri(
            name,
            kwargs.get("version") or "latest",
        )
        return GkeDeployer(config, clients.apps_v1_api, clients.core_v1_api).apply_service(
            name,
            image,
            container_port=kwargs.get("container_port") or 80,
            replicas=kwargs.get("replicas") or 1,
            env=env_refs,
        )

    def _env_sample_keys(self, env_sample_file):
        if not env_sample_file or not os.path.exists(env_sample_file):
            return []
        return list(read_config(open(env_sample_file).read()).keys())
