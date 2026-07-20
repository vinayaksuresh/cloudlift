import json

from click import prompt
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_err
from cloudlift.version import VERSION

CONFIGURATION_KEY_TEMPLATE = 'cloudlift:{environment}:environment'


class AzureEnvironmentConfiguration(object):
    def __init__(self, environment, app_config_client=None):
        self.environment = environment
        self.app_config_client = app_config_client or self._build_app_config_client()

    def get_config(self, cloudlift_version=VERSION):
        try:
            setting = self.app_config_client.get_configuration_setting(
                key=CONFIGURATION_KEY_TEMPLATE.format(environment=self.environment)
            )
            return json.loads(setting.value)
        except Exception as exc:
            raise UnrecoverableException(
                "Azure environment configuration not found. Does this environment exist? {}".format(exc)
            )

    def update_config(self):
        if not self._env_config_exists():
            self._create_config()

    def set_config(self, config):
        return self._set_config(config)

    def _set_config(self, config):
        config.setdefault(self.environment, {})
        config[self.environment].setdefault('provider', 'azure')
        config['cloudlift_version'] = VERSION
        self._validate_changes(config)
        return self._set_setting(
            CONFIGURATION_KEY_TEMPLATE.format(environment=self.environment),
            json.dumps(config)
        )

    def _env_config_exists(self):
        try:
            self.app_config_client.get_configuration_setting(
                key=CONFIGURATION_KEY_TEMPLATE.format(environment=self.environment)
            )
            return True
        except Exception:
            return False

    def _create_config(self):
        subscription_id = prompt('Azure subscription ID')
        resource_group = prompt('Azure resource group', default='cloudlift-{}'.format(self.environment))
        location = prompt('Azure location', default='centralindia')
        managed_environment_name = prompt(
            'Azure Container Apps environment name',
            default='cloudlift-{}-apps'.format(self.environment)
        )
        log_analytics_workspace_name = prompt(
            'Log Analytics workspace name',
            default='cloudlift-{}-logs'.format(self.environment)
        )
        container_registry_name = prompt(
            'Azure Container Registry name',
            default='cloudlift{}acr'.format(self.environment.replace('-', ''))
        )
        key_vault_name = prompt(
            'Azure Key Vault name',
            default='cloudlift-{}-kv'.format(self.environment)
        )
        config_store_endpoint = prompt('Azure App Configuration endpoint')
        environment_configuration = {
            self.environment: {
                'provider': 'azure',
                'subscription_id': subscription_id,
                'resource_group': resource_group,
                'location': location,
                'container_apps_environment_name': managed_environment_name,
                'log_analytics_workspace_name': log_analytics_workspace_name,
                'container_registry_name': container_registry_name,
                'container_registry_login_server': '{}.azurecr.io'.format(container_registry_name),
                'key_vault_name': key_vault_name,
                'app_configuration_endpoint': config_store_endpoint,
                'service_defaults': {
                    'cpu': 0.5,
                    'memory': '1Gi',
                    'min_replicas': 1,
                    'max_replicas': 1,
                    'ingress': 'external'
                }
            },
            'cloudlift_version': VERSION
        }
        self._set_config(environment_configuration)

    def _validate_changes(self, configuration):
        log_bold('\nValidating Azure environment schema..')
        schema = {
            'title': 'azure_environment_configuration',
            'type': 'object',
            'properties': {
                self.environment: {
                    'type': 'object',
                    'properties': {
                        'provider': {'type': 'string', 'pattern': '^azure$'},
                        'subscription_id': {'type': 'string'},
                        'resource_group': {'type': 'string'},
                        'location': {'type': 'string'},
                        'container_apps_environment_name': {'type': 'string'},
                        'container_apps_environment_id': {'type': 'string'},
                        'log_analytics_workspace_name': {'type': 'string'},
                        'log_analytics_workspace_id': {'type': 'string'},
                        'container_registry_name': {'type': 'string'},
                        'container_registry_login_server': {'type': 'string'},
                        'key_vault_name': {'type': 'string'},
                        'key_vault_uri': {'type': 'string'},
                        'app_configuration_endpoint': {'type': 'string'},
                        'service_defaults': {'type': 'object'}
                    },
                    'required': [
                        'provider',
                        'subscription_id',
                        'resource_group',
                        'location',
                        'container_apps_environment_name',
                        'container_registry_name',
                        'container_registry_login_server',
                        'key_vault_name'
                    ]
                },
                'cloudlift_version': {'type': 'string'}
            },
            'required': [self.environment]
        }
        try:
            validate(configuration, schema)
        except ValidationError as validation_error:
            log_err('Schema validation failed!')
            raise UnrecoverableException(validation_error.message)
        log_bold('Schema valid!')

    def _set_setting(self, key, value):
        try:
            from azure.appconfiguration import ConfigurationSetting
            setting = ConfigurationSetting(key=key, value=value)
        except Exception:
            setting = type('ConfigurationSetting', (), {'key': key, 'value': value})()
        return self.app_config_client.set_configuration_setting(setting)

    def _build_app_config_client(self):
        try:
            from azure.appconfiguration import AzureAppConfigurationClient
            from azure.identity import DefaultAzureCredential
            endpoint = prompt('Azure App Configuration endpoint')
            return AzureAppConfigurationClient(endpoint, DefaultAzureCredential())
        except Exception as exc:
            raise UnrecoverableException(
                'Unable to create Azure App Configuration client. {}'.format(exc)
            )
