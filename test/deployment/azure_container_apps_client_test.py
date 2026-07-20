from cloudlift.deployment.azure_container_apps_client import AzureContainerAppsClient


class FakePoller(object):
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


class FakeContainerAppsOperations(object):
    def __init__(self):
        self.calls = []

    def begin_create_or_update(self, resource_group, app_name, payload):
        self.calls.append((resource_group, app_name, payload))
        return FakePoller({'ok': True})


class FakeContainerAppsClient(object):
    def __init__(self):
        self.container_apps = FakeContainerAppsOperations()


def environment_config():
    return {
        'resource_group': 'rg-cloudlift-staging',
        'location': 'centralindia',
        'container_apps_environment_id': '/subscriptions/sub-123/managedEnvironments/staging-apps',
        'container_registry_login_server': 'stagingacr.azurecr.io',
        'tags': {'team': 'platform'}
    }


def service_config():
    return {
        'http_interface': {
            'internal': False,
            'container_port': 8080,
            'health_check_path': '/health',
            'hostnames': ['web.example.com']
        },
        'memory': '2Gi',
        'cpu': 1.0,
        'command': 'bundle exec rackup',
        'min_replicas': 2,
        'max_replicas': 5,
        'env': {'RACK_ENV': 'production'},
        'secrets': {'DATABASE_URL': 'database-url'}
    }


class TestAzureContainerAppsClient(object):
    def test_maps_cloudlift_service_to_container_app_payload(self):
        fake_client = FakeContainerAppsClient()
        client = AzureContainerAppsClient('sub-123', container_apps_client=fake_client)

        client.create_or_update_app(
            environment_config(),
            'Web',
            service_config(),
            'stagingacr.azurecr.io/web-repo:abc123'
        )

        resource_group, app_name, payload = fake_client.container_apps.calls[0]
        container = payload['properties']['template']['containers'][0]
        ingress = payload['properties']['configuration']['ingress']

        assert resource_group == 'rg-cloudlift-staging'
        assert app_name == 'web'
        assert payload['properties']['managedEnvironmentId'].endswith('staging-apps')
        assert container['image'] == 'stagingacr.azurecr.io/web-repo:abc123'
        assert container['command'] == ['bundle exec rackup']
        assert container['resources'] == {'cpu': 1.0, 'memory': '2Gi'}
        assert {'name': 'RACK_ENV', 'value': 'production'} in container['env']
        assert {'name': 'DATABASE_URL', 'secretRef': 'database-url'} in container['env']
        assert ingress['external'] is True
        assert ingress['targetPort'] == 8080
        assert container['probes'][0]['httpGet']['path'] == '/health'
        assert payload['properties']['template']['scale'] == {'minReplicas': 2, 'maxReplicas': 5}
        assert payload['tags']['team'] == 'platform'
