import json

import pytest

from cloudlift.config.azure_environment_configuration import AzureEnvironmentConfiguration
from cloudlift.exceptions import UnrecoverableException


class Setting(object):
    def __init__(self, key, value):
        self.key = key
        self.value = value


class FakeAppConfigurationClient(object):
    def __init__(self):
        self.settings = {}

    def get_configuration_setting(self, key):
        if key not in self.settings:
            raise KeyError(key)
        return Setting(key, self.settings[key])

    def set_configuration_setting(self, setting):
        self.settings[setting.key] = setting.value
        return setting


def azure_environment_config():
    return {
        'staging': {
            'provider': 'azure',
            'subscription_id': 'sub-123',
            'resource_group': 'rg-cloudlift-staging',
            'location': 'centralindia',
            'container_apps_environment_name': 'staging-apps',
            'container_apps_environment_id': '/subscriptions/sub-123/managedEnvironments/staging-apps',
            'log_analytics_workspace_name': 'staging-logs',
            'container_registry_name': 'stagingacr',
            'container_registry_login_server': 'stagingacr.azurecr.io',
            'key_vault_name': 'staging-kv',
            'key_vault_uri': 'https://staging-kv.vault.azure.net/',
            'app_configuration_endpoint': 'https://staging.azconfig.io',
            'service_defaults': {'cpu': 0.5, 'memory': '1Gi'}
        }
    }


class TestAzureEnvironmentConfiguration(object):
    def test_set_config_stores_provider_and_version(self):
        client = FakeAppConfigurationClient()
        config = AzureEnvironmentConfiguration('staging', app_config_client=client)

        config.set_config(azure_environment_config())
        stored = json.loads(client.settings['cloudlift:staging:environment'])

        assert stored['staging']['provider'] == 'azure'
        assert 'cloudlift_version' in stored

    def test_get_config_reads_json_from_app_configuration(self):
        client = FakeAppConfigurationClient()
        expected = azure_environment_config()
        client.settings['cloudlift:staging:environment'] = json.dumps(expected)

        response = AzureEnvironmentConfiguration('staging', app_config_client=client).get_config()

        assert response == expected

    def test_invalid_provider_fails_validation(self):
        client = FakeAppConfigurationClient()
        invalid = azure_environment_config()
        invalid['staging']['provider'] = 'aws'

        with pytest.raises(UnrecoverableException):
            AzureEnvironmentConfiguration('staging', app_config_client=client).set_config(invalid)
