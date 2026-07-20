from cloudlift.deployment import azure_service_updater


class FakeAzureEnvironmentConfiguration(object):
    def __init__(self, environment):
        self.environment = environment

    def get_config(self):
        return {
            self.environment: {
                'subscription_id': 'sub-123',
                'resource_group': 'rg-cloudlift-staging',
                'location': 'centralindia',
                'container_apps_environment_id': '/subscriptions/sub-123/managedEnvironments/staging-apps',
                'container_registry_name': 'stagingacr',
                'container_registry_login_server': 'stagingacr.azurecr.io'
            }
        }


class FakeAzureServiceConfiguration(object):
    def __init__(self, name, environment):
        self.name = name
        self.environment = environment

    def get_config(self):
        return {
            'services': {
                'Web': {
                    'http_interface': {'internal': False, 'container_port': 80},
                    'memory': '1Gi',
                    'cpu': 0.5,
                    'command': None,
                    'env': {}
                }
            }
        }


class FakeRegistryClient(object):
    calls = []

    def __init__(self, name, environment_config, version, build_args, working_dir):
        self.__class__.calls.append((name, environment_config, version, build_args, working_dir))

    def build_and_push_image(self):
        return 'stagingacr.azurecr.io/web-repo:abc123'


class FakeContainerAppsClient(object):
    calls = []

    def __init__(self, subscription_id):
        self.subscription_id = subscription_id

    def create_or_update_app(self, environment_config, service_name, service_config, image):
        self.__class__.calls.append((self.subscription_id, environment_config, service_name, service_config, image))


class TestAzureServiceUpdater(object):
    def test_builds_pushes_and_updates_container_app_revision(self, monkeypatch, tmp_path):
        env_sample = tmp_path / 'env.sample'
        env_sample.write_text('RACK_ENV=production\n')
        FakeRegistryClient.calls = []
        FakeContainerAppsClient.calls = []
        monkeypatch.setattr(
            azure_service_updater,
            'AzureEnvironmentConfiguration',
            FakeAzureEnvironmentConfiguration
        )
        monkeypatch.setattr(
            azure_service_updater,
            'AzureServiceConfiguration',
            FakeAzureServiceConfiguration
        )

        updater = azure_service_updater.AzureServiceUpdater(
            'web',
            'staging',
            str(env_sample),
            version='abc123',
            build_args={'RAILS_ENV': 'production'},
            registry_client_class=FakeRegistryClient,
            container_apps_client_class=FakeContainerAppsClient
        )
        updater.run()

        assert FakeRegistryClient.calls[0][0] == 'web'
        assert FakeRegistryClient.calls[0][2] == 'abc123'
        assert FakeContainerAppsClient.calls[0][0] == 'sub-123'
        assert FakeContainerAppsClient.calls[0][2] == 'Web'
        assert FakeContainerAppsClient.calls[0][4] == 'stagingacr.azurecr.io/web-repo:abc123'
