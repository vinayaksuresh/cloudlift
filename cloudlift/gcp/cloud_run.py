import os

from cloudlift.deployment.deployer import read_config
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_intent, log_warning
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration
from cloudlift.gcp.secrets import GcpSecretManagerStore


class CloudRunClient(object):
    def __init__(self, project_id, region, client=None):
        self.project_id = project_id
        self.region = region
        self.client = client or self._build_client()

    def deploy_service(self, service_name, image_uri, secret_references, service_defaults=None):
        service_defaults = service_defaults or {}
        parent = self.parent_path
        full_name = '{}/services/{}'.format(parent, service_name)
        service = self._service_body(full_name, service_name, image_uri, secret_references, service_defaults)
        try:
            self.client.get_service(request={'name': full_name})
            operation = self.client.update_service(request={'service': service})
        except Exception as err:
            if not self._is_not_found(err):
                raise UnrecoverableException('Unable to read Cloud Run service: ' + str(err))
            operation = self.client.create_service(
                request={
                    'parent': parent,
                    'service_id': service_name,
                    'service': service
                }
            )
        try:
            deployed_service = operation.result()
        except Exception as err:
            raise UnrecoverableException('Cloud Run deployment failed: ' + str(err))
        return {
            'url': getattr(deployed_service, 'uri', None) or getattr(deployed_service, 'url', None),
            'revision': self._latest_revision(deployed_service),
            'service': deployed_service
        }

    @property
    def parent_path(self):
        return 'projects/{}/locations/{}'.format(self.project_id, self.region)

    def _service_body(self, full_name, service_name, image_uri, secret_references, service_defaults):
        container = {
            'image': image_uri,
            'env': self._env_vars(secret_references),
            'resources': {
                'limits': {
                    'cpu': str(service_defaults.get('cpu', '1')),
                    'memory': service_defaults.get('memory', '512Mi')
                }
            }
        }
        template = {
            'containers': [container],
            'max_instance_request_concurrency': service_defaults.get('concurrency', 80)
        }
        if service_defaults.get('service_account'):
            template['service_account'] = service_defaults['service_account']
        if service_defaults.get('vpc_connector'):
            template['vpc_access'] = {'connector': service_defaults['vpc_connector']}
        service = {
            'name': full_name,
            'template': template,
            'labels': {'cloudlift_service': service_name}
        }
        if service_defaults.get('ingress'):
            service['ingress'] = service_defaults['ingress']
        return service

    def _env_vars(self, secret_references):
        env_vars = []
        for key, reference in sorted(secret_references.items()):
            secret_name, version = reference.rsplit(':', 1)
            env_vars.append({
                'name': key,
                'value_source': {
                    'secret_key_ref': {
                        'secret': secret_name,
                        'version': version
                    }
                }
            })
        return env_vars

    def _latest_revision(self, service):
        template = getattr(service, 'template', None)
        revision = getattr(template, 'revision', None) if template else None
        return revision or getattr(service, 'latest_ready_revision', None) or getattr(service, 'latest_created_revision', None)

    def _is_not_found(self, err):
        code = getattr(err, 'code', None)
        if callable(code):
            try:
                return code().name == 'NOT_FOUND'
            except Exception:
                return False
        return type(err).__name__ in ['NotFound', 'ResourceNotFound'] or 'not found' in str(err).lower()

    def _build_client(self):
        from google.cloud import run_v2
        return run_v2.ServicesClient()


class CloudRunServiceUpdater(object):
    def __init__(self, name, environment, env_sample_file=None, version=None, build_args=None, working_dir='.',
                 configuration_class=GcpEnvironmentConfiguration, secret_store_class=GcpSecretManagerStore,
                 artifact_registry_client_class=ArtifactRegistryClient, cloud_run_client_class=CloudRunClient):
        self.name = name
        self.environment = environment
        self.env_sample_file = env_sample_file or './env.sample'
        self.version = version
        self.build_args = build_args or {}
        self.working_dir = working_dir
        self.configuration_class = configuration_class
        self.secret_store_class = secret_store_class
        self.artifact_registry_client_class = artifact_registry_client_class
        self.cloud_run_client_class = cloud_run_client_class

    def run(self):
        if not os.path.exists(self.env_sample_file):
            raise UnrecoverableException('env.sample not found. Exiting.')
        config = self.configuration_class(self.environment).get_config()
        self._validate_config(config)
        service_config = read_config(open(self.env_sample_file).read())
        secret_store = self.secret_store_class(self.name, self.environment, config['project_id'])
        _, secret_paths = secret_store.get_existing_config()
        self._validate_secrets(service_config, secret_paths)
        artifact_registry = config['artifact_registry']
        image_client = self.artifact_registry_client_class(
            self.name,
            config['project_id'],
            artifact_registry['location'],
            artifact_registry['repository'],
            self.version,
            self.build_args,
            self.working_dir
        )
        log_warning('Deploying to GCP Cloud Run in {}'.format(config['region']))
        image_uri = image_client.build_and_upload_image()
        cloud_run_client = self.cloud_run_client_class(config['project_id'], config['region'])
        result = cloud_run_client.deploy_service(
            self.name,
            image_uri,
            {key: secret_paths[key] for key in service_config},
            config.get('service_defaults', {})
        )
        log_bold(self.name + ' deployed to Cloud Run successfully.')
        if result.get('url'):
            log_intent('URL: ' + result['url'])
        if result.get('revision'):
            log_intent('Revision: ' + result['revision'])
        return result

    def _validate_config(self, config):
        for key in ['project_id', 'region', 'artifact_registry']:
            if not config.get(key):
                raise UnrecoverableException('Missing GCP configuration: ' + key)
        for key in ['location', 'repository']:
            if not config['artifact_registry'].get(key):
                raise UnrecoverableException('Missing GCP Artifact Registry configuration: ' + key)

    def _validate_secrets(self, service_config, secret_paths):
        missing_secret_config = set(service_config) - set(secret_paths)
        if missing_secret_config:
            raise UnrecoverableException('There is no GCP secret value for the keys ' + str(missing_secret_config))
        missing_env_sample_config = set(secret_paths) - set(service_config)
        if missing_env_sample_config:
            raise UnrecoverableException('There is no config value for the keys in env.sample file ' + str(missing_env_sample_config))
