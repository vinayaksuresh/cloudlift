import json
import os

from jsonschema import validate
from jsonschema.exceptions import ValidationError
from stringcase import pascalcase

from cloudlift.config.azure_environment_configuration import AzureEnvironmentConfiguration
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_err
from cloudlift.version import VERSION

SERVICE_KEY_TEMPLATE = 'cloudlift:{environment}:service:{service_name}'
AZURE_UNSUPPORTED_FIELDS = (
    'volume',
    'spot_deployment',
    'custom_metrics',
    'sidecars',
    'depends_on',
    'logging',
    'disable_service_alarms'
)


class AzureServiceConfiguration(object):
    def __init__(self, service_name, environment, app_config_client=None, secret_client=None):
        self.service_name = service_name
        self.environment = environment
        self.app_config_client = app_config_client or self._build_app_config_client()
        self.secret_client = secret_client
        self.new_service = False
        self.environment_configuration = AzureEnvironmentConfiguration(
            environment,
            app_config_client=self.app_config_client
        ).get_config().get(environment, {})
        self.service_defaults = self.environment_configuration.get('service_defaults', {})

    def edit_config(self):
        # Keep the same public method as AWS ServiceConfiguration. Azure starts
        # with defaults and stores them; interactive editing can be added on top
        # without changing callers.
        config = self.get_config(VERSION)
        self.set_config(config)

    def get_config(self, cloudlift_version=VERSION):
        try:
            setting = self.app_config_client.get_configuration_setting(
                key=SERVICE_KEY_TEMPLATE.format(
                    environment=self.environment,
                    service_name=self.service_name
                )
            )
            return json.loads(setting.value)
        except Exception:
            self.new_service = True
            return self._default_service_configuration()

    def set_config(self, config):
        config['cloudlift_version'] = VERSION
        self._validate_changes(config)
        return self._set_setting(
            SERVICE_KEY_TEMPLATE.format(
                environment=self.environment,
                service_name=self.service_name
            ),
            json.dumps(config)
        )

    def update_cloudlift_version(self):
        config = self.get_config(VERSION)
        self.set_config(config)

    def _validate_changes(self, configuration):
        for service_name, service_config in configuration.get('services', {}).items():
            unsupported = sorted(set(service_config.keys()).intersection(AZURE_UNSUPPORTED_FIELDS))
            if unsupported:
                raise UnrecoverableException(
                    'Azure Container Apps does not support these AWS-only Cloudlift fields for {}: {}'.format(
                        service_name,
                        ', '.join(unsupported)
                    )
                )
        schema = {
            'title': 'azure_service_configuration',
            'type': 'object',
            'properties': {
                'services': {'type': 'object'},
                'cloudlift_version': {'type': 'string'},
                'tags': {'type': 'object'}
            },
            'required': ['services', 'cloudlift_version']
        }
        try:
            validate(configuration, schema)
        except ValidationError as validation_error:
            log_err('Schema validation failed!')
            raise UnrecoverableException(validation_error.message)
        log_bold('Schema valid!')

    def _default_service_configuration(self):
        return {
            'services': {
                pascalcase(self.service_name): {
                    'http_interface': {
                        'internal': False,
                        'container_port': 80,
                        'health_check_path': '/elb-check',
                        'hostnames': []
                    },
                    'memory': self.service_defaults.get('memory', '1Gi'),
                    'cpu': self.service_defaults.get('cpu', 0.5),
                    'command': None,
                    'min_replicas': self.service_defaults.get('min_replicas', 1),
                    'max_replicas': self.service_defaults.get('max_replicas', 1),
                    'env': {}
                }
            }
        }

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
            endpoint = os.environ.get('AZURE_APPCONFIG_ENDPOINT')
            return AzureAppConfigurationClient(endpoint, DefaultAzureCredential())
        except Exception as exc:
            raise UnrecoverableException(
                'Unable to create Azure App Configuration client. {}'.format(exc)
            )
