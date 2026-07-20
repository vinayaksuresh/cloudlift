import pytest

from cloudlift.config import environment_configuration
from cloudlift.config.provider import ProviderResolver, AWS_PROVIDER, AZURE_PROVIDER
from cloudlift.exceptions import UnrecoverableException


class FakeEnvironmentConfiguration(object):
    config = {}

    def __init__(self, environment):
        self.environment = environment

    def get_config(self):
        return {self.environment: self.config}


class TestProviderResolver(object):
    def test_default_provider_is_aws(self):
        assert ProviderResolver.validate(None) == AWS_PROVIDER

    def test_rejects_unknown_provider(self):
        with pytest.raises(UnrecoverableException):
            ProviderResolver.validate('gcp')

    def test_missing_provider_in_existing_environment_resolves_to_aws(self, monkeypatch):
        FakeEnvironmentConfiguration.config = {'region': 'ap-south-1'}
        monkeypatch.setattr(
            environment_configuration,
            'EnvironmentConfiguration',
            FakeEnvironmentConfiguration
        )

        provider = ProviderResolver.from_environment_config('staging')

        assert provider.provider == AWS_PROVIDER

    def test_azure_provider_in_existing_environment_resolves_to_azure(self, monkeypatch):
        FakeEnvironmentConfiguration.config = {'provider': AZURE_PROVIDER}
        monkeypatch.setattr(
            environment_configuration,
            'EnvironmentConfiguration',
            FakeEnvironmentConfiguration
        )

        provider = ProviderResolver.from_environment_config('staging')

        assert provider.provider == AZURE_PROVIDER
        assert provider.environment_creator.__name__ == 'AzureEnvironmentCreator'
