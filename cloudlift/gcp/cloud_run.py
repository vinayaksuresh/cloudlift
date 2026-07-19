import os

from cloudlift.config.logging import log_bold, log_err, log_intent
from cloudlift.deployment.deployer import read_config
from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration
from cloudlift.gcp.secrets import GcpSecretManagerStore


class CloudRunClient(object):
    def __init__(self, project_id, region, client=None):
        self.project_id = project_id
        self.region = region
        self.client = client or self._default_client()

    def deploy_service(self, service_name, image_uri, environment_config, secret_references):
        service = self._service_request(service_name, image_uri, environment_config, secret_references)
        parent = 'projects/%s/locations/%s' % (self.project_id, self.region)
        try:
            operation = self.client.update_service(request={'service': service})
        except Exception as error:
            if type(error).__name__ != 'NotFound':
                raise UnrecoverableException('Cloud Run deployment failed: %s' % error)
            operation = self.client.create_service(
                request={'parent': parent, 'service': service, 'service_id': service_name}
            )
        try:
            response = operation.result()
        except Exception as error:
            raise UnrecoverableException('Cloud Run deployment failed: %s' % error)
        if isinstance(response, dict):
            url = response.get('uri')
            revision = response.get('latest_ready_revision')
        else:
            url = getattr(response, 'uri', None)
            revision = getattr(response, 'latest_ready_revision', None)
        return {'url': url, 'revision': revision}

    def _service_request(self, service_name, image_uri, environment_config, secret_references):
        cloud_run_config = environment_config.get('cloud_run', {})
        defaults = cloud_run_config.get('service_defaults', {})
        container = {
            'image': image_uri,
            'env': secret_references,
            'resources': {
                'limits': {
                    'cpu': defaults.get('cpu', '1'),
                    'memory': defaults.get('memory', '512Mi'),
                }
            },
        }
        if defaults.get('concurrency'):
            container['max_instance_request_concurrency'] = defaults.get('concurrency')
        service = {
            'name': 'projects/%s/locations/%s/services/%s' % (self.project_id, self.region, service_name),
            'template': {
                'containers': [container],
                'scaling': {
                    'min_instance_count': defaults.get('min_instances', 0),
                    'max_instance_count': defaults.get('max_instances', 100),
                },
            },
            'ingress': cloud_run_config.get('ingress', 'INGRESS_TRAFFIC_ALL'),
        }
        if defaults.get('timeout'):
            service['template']['timeout'] = defaults.get('timeout')
        if cloud_run_config.get('service_account'):
            service['template']['service_account'] = cloud_run_config['service_account']
        if cloud_run_config.get('vpc_connector'):
            service['template']['vpc_access'] = {'connector': cloud_run_config['vpc_connector']}
        return service

    def _default_client(self):
        try:
            from google.cloud import run_v2
        except ImportError:
            raise UnrecoverableException('google-cloud-run is required for Cloud Run support.')
        return run_v2.ServicesClient()


class CloudRunServiceUpdater(object):
    def __init__(self, name, environment, env_sample_file=None, version=None,
                 build_args=None, working_dir='.', environment_configuration_cls=None,
                 secrets_store_cls=None, artifact_registry_client_cls=None,
                 cloud_run_client_cls=None):
        self.name = name
        self.environment = environment
        self.env_sample_file = env_sample_file or './env.sample'
        self.version = version
        self.build_args = build_args
        self.working_dir = working_dir
        self.environment_configuration_cls = environment_configuration_cls or GcpEnvironmentConfiguration
        self.secrets_store_cls = secrets_store_cls or GcpSecretManagerStore
        self.artifact_registry_client_cls = artifact_registry_client_cls or ArtifactRegistryClient
        self.cloud_run_client_cls = cloud_run_client_cls or CloudRunClient

    def run(self):
        if not os.path.exists(self.env_sample_file):
            raise UnrecoverableException('env.sample not found. Exiting.')
        environment_config = self.environment_configuration_cls(self.environment).get_config()
        project_id = environment_config['project_id']
        region = environment_config['region']
        artifact_registry = environment_config['artifact_registry']
        service_config = read_config(open(self.env_sample_file).read())
        secrets_store = self.secrets_store_cls(self.name, self.environment, project_id)
        _, environment_config_paths = secrets_store.get_existing_config()
        missing_env_config = set(service_config) - set(environment_config_paths)
        if missing_env_config:
            raise UnrecoverableException('There is no config value for the keys ' + str(missing_env_config))
        missing_env_sample_config = set(environment_config_paths) - set(service_config)
        if missing_env_sample_config:
            raise UnrecoverableException('There is no config value for the keys in env.sample file ' + str(missing_env_sample_config))
        secret_references = secrets_store.cloud_run_secret_references(service_config)
        artifact_registry_client = self.artifact_registry_client_cls(
            self.name,
            project_id,
            artifact_registry['location'],
            artifact_registry['repository'],
            self.build_args,
            self.working_dir,
        )
        image_uri = artifact_registry_client.build_and_upload_image(self.version)
        log_bold('Initiating Cloud Run deployment')
        result = self.cloud_run_client_cls(project_id, region).deploy_service(
            self.name,
            image_uri,
            environment_config,
            secret_references,
        )
        if result:
            log_bold(self.name + ' deployed to Cloud Run successfully.')
            if result.get('url'):
                log_intent('Cloud Run URL: ' + result['url'])
            if result.get('revision'):
                log_intent('Cloud Run revision: ' + result['revision'])
            return result
        log_err(self.name + ' Cloud Run deployment failed.')
        raise UnrecoverableException('Cloud Run deployment failed')
