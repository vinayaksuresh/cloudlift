import os

from cloudlift.config.logging import log_bold, log_intent
from cloudlift.deployment.deployer import make_container_defn_env_conf, read_config
from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration
from cloudlift.gcp.secrets import GcpSecretManagerStore


class CloudRunClient(object):
    """Thin wrapper around Cloud Run v2 ServicesClient."""

    def __init__(self, project_id, region, client=None):
        self.project_id = project_id
        self.region = region
        self.client = client or self._build_client()

    def _build_client(self):
        try:
            from google.cloud import run_v2
        except ImportError:
            raise UnrecoverableException("google-cloud-run is required for GCP Cloud Run deployments.")
        return run_v2.ServicesClient()

    @property
    def parent(self):
        return "projects/%s/locations/%s" % (self.project_id, self.region)

    def service_name(self, service):
        return "%s/services/%s" % (self.parent, service)

    def deploy_service(self, service, image_uri, env_secret_refs, cloud_run_config):
        service_resource = self._build_service_resource(service, image_uri, env_secret_refs, cloud_run_config)
        try:
            self.client.get_service(request={"name": self.service_name(service)})
            operation = self.client.update_service(request={"service": service_resource})
        except Exception as error:
            if "NotFound" not in type(error).__name__ and "not found" not in str(error).lower():
                raise UnrecoverableException("Cloud Run service lookup failed: %s" % error)
            operation = self.client.create_service(
                request={"parent": self.parent, "service": service_resource, "service_id": service}
            )
        try:
            deployed_service = operation.result()
        except Exception as error:
            raise UnrecoverableException("Cloud Run deployment failed: %s" % error)
        if not self._revision_ready(deployed_service):
            raise UnrecoverableException("Cloud Run deployment did not produce a ready revision.")
        return deployed_service

    def _build_service_resource(self, service, image_uri, env_secret_refs, cloud_run_config):
        try:
            from google.cloud import run_v2
        except ImportError:
            raise UnrecoverableException("google-cloud-run is required for GCP Cloud Run deployments.")

        env = []
        for key, secret_ref in sorted(env_secret_refs.items()):
            secret_id = secret_ref.split("/secrets/")[1].split("/")[0]
            version = secret_ref.split("/versions/")[1]
            env.append(run_v2.EnvVar(
                name=key,
                value_source=run_v2.EnvVarSource(
                    secret_key_ref=run_v2.SecretKeySelector(secret=secret_id, version=version)
                )
            ))

        container = run_v2.Container(
            image=image_uri,
            env=env,
            resources=run_v2.ResourceRequirements(
                limits={
                    "cpu": str(cloud_run_config.get("cpu", "1")),
                    "memory": str(cloud_run_config.get("memory", "512Mi"))
                }
            )
        )
        template = run_v2.RevisionTemplate(
            containers=[container],
            max_instance_request_concurrency=cloud_run_config.get("concurrency", 80),
            service_account=cloud_run_config.get("service_account") or "",
            vpc_access=run_v2.VpcAccess(connector=cloud_run_config.get("vpc_connector") or "")
        )
        return run_v2.Service(
            name=self.service_name(service),
            template=template,
            ingress=cloud_run_config.get("ingress", "INGRESS_TRAFFIC_ALL")
        )

    def _revision_ready(self, deployed_service):
        if getattr(deployed_service, "latest_ready_revision", None):
            return True
        conditions = getattr(deployed_service, "conditions", []) or []
        for condition in conditions:
            if getattr(condition, "type", None) == "Ready" and str(getattr(condition, "state", "")).endswith("TRUE"):
                return True
        return bool(getattr(deployed_service, "uri", None))


class CloudRunServiceUpdater(object):
    def __init__(self, name, environment, env_sample_file=None, version=None,
                 build_args=None, working_dir='.', config=None, secret_store=None,
                 artifact_registry_client=None, cloud_run_client=None):
        self.name = name
        self.environment = environment
        self.env_sample_file = env_sample_file or './env.sample'
        self.version = version
        self.build_args = build_args or {}
        self.working_dir = working_dir
        self.config = config
        self.secret_store = secret_store
        self.artifact_registry_client = artifact_registry_client
        self.cloud_run_client = cloud_run_client

    def run(self):
        if not os.path.exists(self.env_sample_file):
            raise UnrecoverableException('env.sample not found. Exiting.')
        config = self.config or GcpEnvironmentConfiguration(self.environment).get_config()
        service_config = read_config(open(self.env_sample_file).read())
        secret_store = self.secret_store or GcpSecretManagerStore(
            self.name, self.environment, config["project_id"]
        )
        _, environment_config_paths = secret_store.get_existing_config()
        missing_env_config = set(service_config) - set(environment_config_paths)
        if missing_env_config:
            raise UnrecoverableException('There is no config value for the keys ' + str(missing_env_config))
        missing_env_sample_config = set(environment_config_paths) - set(service_config)
        if missing_env_sample_config:
            raise UnrecoverableException('There is no config value for the keys in env.sample file ' + str(missing_env_sample_config))

        env_secret_refs = dict(make_container_defn_env_conf(service_config, environment_config_paths))
        artifact_registry = config["artifact_registry"]
        image_client = self.artifact_registry_client or ArtifactRegistryClient(
            self.name,
            config["project_id"],
            artifact_registry["location"],
            artifact_registry["repository"],
            self.version,
            self.build_args,
            self.working_dir
        )
        image_uri = image_client.build_and_upload_image()
        cloud_run_client = self.cloud_run_client or CloudRunClient(config["project_id"], config["region"])
        deployed_service = cloud_run_client.deploy_service(
            self.name,
            image_uri,
            env_secret_refs,
            config.get("cloud_run", {})
        )
        log_bold("%s deployed successfully to Cloud Run." % self.name)
        if getattr(deployed_service, "uri", None):
            log_intent("URL: %s" % deployed_service.uri)
        if getattr(deployed_service, "latest_ready_revision", None):
            log_intent("Revision: %s" % deployed_service.latest_ready_revision)
        return deployed_service
