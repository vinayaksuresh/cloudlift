import os

from cloudlift.config.logging import log_bold, log_intent
from cloudlift.deployment.deployer import read_config
from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration
from cloudlift.gcp.secrets import GcpSecretManagerStore


class CloudRunClient(object):
    def __init__(self, project_id, region, client=None):
        self.project_id = project_id
        self.region = region
        self.client = client or self._build_client()

    def deploy_service(self, service_name, image_uri, secret_env_vars,
                       service_defaults=None):
        service_defaults = service_defaults or {}
        parent = 'projects/%s/locations/%s' % (self.project_id, self.region)
        full_service_name = '%s/services/%s' % (parent, service_name)
        service = self._build_service(full_service_name, image_uri,
                                      secret_env_vars, service_defaults)
        try:
            self.client.get_service(request={'name': full_service_name})
            operation = self.client.update_service(request={'service': service})
        except Exception as error:
            if not self._is_not_found(error):
                raise UnrecoverableException('Cloud Run service lookup failed: %s' % error)
            operation = self.client.create_service(request={
                'parent': parent,
                'service_id': service_name,
                'service': service,
            })
        try:
            result = operation.result() if hasattr(operation, 'result') else operation
        except Exception as error:
            raise UnrecoverableException('Cloud Run deployment failed: %s' % error)
        return self._deployment_result(result)

    def _build_service(self, name, image_uri, secret_env_vars, service_defaults):
        container = {
            'image': image_uri,
            'env': [
                {
                    'name': key,
                    'value_source': {
                        'secret_key_ref': {
                            'secret': ref['secret'],
                            'version': ref.get('version', 'latest'),
                        }
                    },
                }
                for key, ref in sorted(secret_env_vars.items())
            ],
            'resources': {
                'limits': {
                    'cpu': service_defaults.get('cpu', '1000m'),
                    'memory': service_defaults.get('memory', '512Mi'),
                }
            },
        }
        template = {
            'containers': [container],
            'max_instance_request_concurrency': service_defaults.get('concurrency', 80),
        }
        if service_defaults.get('service_account'):
            template['service_account'] = service_defaults['service_account']
        if service_defaults.get('vpc_connector'):
            template['vpc_access'] = {'connector': service_defaults['vpc_connector']}
        service = {
            'name': name,
            'template': template,
            'ingress': service_defaults.get('ingress', 'INGRESS_TRAFFIC_ALL'),
        }
        return service

    def _deployment_result(self, result):
        if isinstance(result, dict):
            return {
                'name': result.get('name'),
                'url': result.get('uri') or result.get('url'),
                'revision': result.get('latest_ready_revision') or result.get('latestReadyRevision'),
            }
        return {
            'name': getattr(result, 'name', None),
            'url': getattr(result, 'uri', None) or getattr(result, 'url', None),
            'revision': getattr(result, 'latest_ready_revision', None),
        }

    def _is_not_found(self, error):
        if type(error).__name__ == 'NotFound':
            return True
        return 'not found' in str(error).lower() or '404' in str(error)

    def _build_client(self):
        from google.cloud import run_v2
        return run_v2.ServicesClient()


class CloudRunServiceUpdater(object):
    def __init__(self, name, environment, env_sample_file=None, version=None,
                 build_args=None, working_dir='.', config=None,
                 secret_store=None, artifact_registry_client=None,
                 cloud_run_client=None):
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
        service_defaults = config.get('service_defaults', {})
        artifact_registry = config['artifact_registry']
        secret_store = self.secret_store or GcpSecretManagerStore(
            self.name,
            self.environment,
            config['project_id'],
        )
        env_config = self._build_secret_env_config(secret_store)
        artifact_client = self.artifact_registry_client or ArtifactRegistryClient(
            self.name,
            config['project_id'],
            artifact_registry['location'],
            artifact_registry['repository'],
            version=self.version,
            build_args=self.build_args,
            working_dir=self.working_dir,
        )
        log_intent('name: ' + self.name + ' | environment: ' + self.environment)
        image_uri = artifact_client.build_and_upload_image()
        cloud_run_client = self.cloud_run_client or CloudRunClient(
            config['project_id'],
            config['region'],
        )
        deployment = cloud_run_client.deploy_service(
            self.name,
            image_uri,
            env_config,
            service_defaults,
        )
        log_bold(self.name + ' deployed to Cloud Run successfully.')
        if deployment.get('url'):
            log_bold('URL: ' + deployment['url'])
        if deployment.get('revision'):
            log_bold('Revision: ' + deployment['revision'])
        return deployment

    def _build_secret_env_config(self, secret_store):
        service_config = read_config(open(self.env_sample_file).read())
        try:
            environment_config, environment_config_paths = secret_store.get_existing_config()
        except Exception as err:
            log_intent(str(err))
            raise UnrecoverableException(
                'Cannot find the configuration in GCP Secret Manager [env: %s | service: %s].' % (
                    self.environment,
                    self.name,
                )
            )
        missing_env_config = set(service_config) - set(environment_config)
        if missing_env_config:
            raise UnrecoverableException('There is no config value for the keys ' + str(missing_env_config))
        missing_env_sample_config = set(environment_config) - set(service_config)
        if missing_env_sample_config:
            raise UnrecoverableException('There is no config value for the keys in env.sample file ' + str(missing_env_sample_config))
        return {
            env_var_name: environment_config_paths[env_var_name]
            for env_var_name in service_config
        }
