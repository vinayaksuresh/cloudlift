import json

import pytest

from cloudlift.config.azure_service_configuration import AzureServiceConfiguration
from cloudlift.exceptions import UnrecoverableException
from test.config.azure_environment_configuration_test import FakeAppConfigurationClient, azure_environment_config


def service_config():
    return {
        'services': {
            'Web': {
                'http_interface': {
                    'internal': False,
                    'container_port': 8080,
                    'health_check_path': '/health',
                    'hostnames': ['web.example.com']
                },
                'memory': '1Gi',
                'cpu': 0.5,
                'command': 'bundle exec rackup',
                'min_replicas': 1,
                'max_replicas': 3,
                'env': {'RACK_ENV': 'production'},
                'secrets': {'DATABASE_URL': 'database-url'}
            }
        }
    }


class TestAzureServiceConfiguration(object):
    def setup_client(self):
        client = FakeAppConfigurationClient()
        client.settings['cloudlift:staging:environment'] = json.dumps(azure_environment_config())
        return client

    def test_set_and_get_service_config(self):
        client = self.setup_client()
        configuration = AzureServiceConfiguration('web', 'staging', app_config_client=client)

        configuration.set_config(service_config())
        response = configuration.get_config()

        assert response['services']['Web']['env']['RACK_ENV'] == 'production'
        assert response['cloudlift_version']

    def test_default_service_config_uses_container_apps_fields(self):
        client = self.setup_client()
        configuration = AzureServiceConfiguration('web', 'staging', app_config_client=client)

        response = configuration.get_config()

        assert response['services']['Web']['cpu'] == 0.5
        assert response['services']['Web']['memory'] == '1Gi'
        assert response['services']['Web']['http_interface']['container_port'] == 80

    def test_aws_only_fields_fail_validation_for_azure(self):
        client = self.setup_client()
        configuration = AzureServiceConfiguration('web', 'staging', app_config_client=client)
        invalid = service_config()
        invalid['services']['Web']['volume'] = {'efs_id': 'fs-123'}

        with pytest.raises(UnrecoverableException):
            configuration.set_config(invalid)
