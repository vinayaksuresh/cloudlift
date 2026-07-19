import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.cloud_run import CloudRunClient, CloudRunServiceUpdater


ENVIRONMENT_CONFIG = {
    'project_id': 'demo-project',
    'region': 'us-central1',
    'artifact_registry': {'location': 'us', 'repository': 'services'},
    'cloud_run': {
        'service_account': 'run@demo-project.iam.gserviceaccount.com',
        'ingress': 'INGRESS_TRAFFIC_ALL',
        'service_defaults': {
            'cpu': '1',
            'memory': '512Mi',
            'concurrency': 80,
            'min_instances': 0,
            'max_instances': 10,
        },
    },
}


class FakeEnvironmentConfiguration(object):
    def __init__(self, environment):
        self.environment = environment

    def get_config(self):
        return ENVIRONMENT_CONFIG


class FakeSecretsStore(object):
    references = [{'name': 'PORT', 'value_source': {'secret_key_ref': {'secret': 'secret-ref', 'version': 'latest'}}}]
    paths = {'PORT': 'secret-ref'}

    def __init__(self, service_name, environment, project_id):
        self.service_name = service_name
        self.environment = environment
        self.project_id = project_id

    def get_existing_config(self):
        return {'PORT': '8080'}, self.paths

    def cloud_run_secret_references(self, service_config):
        self.__class__.service_config = service_config
        return self.references


class FakeArtifactRegistryClient(object):
    calls = []

    def __init__(self, service_name, project_id, location, repository, build_args, working_dir):
        self.__class__.calls.append((service_name, project_id, location, repository, build_args, working_dir))

    def build_and_upload_image(self, version):
        self.__class__.version = version
        return 'us-docker.pkg.dev/demo-project/services/checkout-api:v1'


class FakeCloudRunClient(object):
    calls = []

    def __init__(self, project_id, region):
        self.project_id = project_id
        self.region = region

    def deploy_service(self, service_name, image_uri, environment_config, secret_references):
        self.__class__.calls.append((self.project_id, self.region, service_name, image_uri, environment_config, secret_references))
        return {'url': 'https://checkout.example.run.app', 'revision': 'checkout-api-00001'}


def test_cloud_run_service_updater_builds_image_and_deploys_with_secrets(tmp_path):
    env_sample = tmp_path / 'env.sample'
    env_sample.write_text('PORT=\n')
    FakeArtifactRegistryClient.calls = []
    FakeCloudRunClient.calls = []

    result = CloudRunServiceUpdater(
        'checkout-api',
        'staging',
        str(env_sample),
        'v1',
        {'RAILS_ENV': 'production'},
        environment_configuration_cls=FakeEnvironmentConfiguration,
        secrets_store_cls=FakeSecretsStore,
        artifact_registry_client_cls=FakeArtifactRegistryClient,
        cloud_run_client_cls=FakeCloudRunClient,
    ).run()

    assert result['url'] == 'https://checkout.example.run.app'
    assert FakeArtifactRegistryClient.calls == [
        ('checkout-api', 'demo-project', 'us', 'services', {'RAILS_ENV': 'production'}, '.')
    ]
    assert FakeArtifactRegistryClient.version == 'v1'
    assert FakeCloudRunClient.calls == [
        (
            'demo-project',
            'us-central1',
            'checkout-api',
            'us-docker.pkg.dev/demo-project/services/checkout-api:v1',
            ENVIRONMENT_CONFIG,
            FakeSecretsStore.references,
        )
    ]


def test_cloud_run_service_updater_fails_when_secret_missing(tmp_path):
    env_sample = tmp_path / 'env.sample'
    env_sample.write_text('PORT=\nMISSING=\n')

    with pytest.raises(UnrecoverableException) as error:
        CloudRunServiceUpdater(
            'checkout-api',
            'staging',
            str(env_sample),
            'v1',
            environment_configuration_cls=FakeEnvironmentConfiguration,
            secrets_store_cls=FakeSecretsStore,
            artifact_registry_client_cls=FakeArtifactRegistryClient,
            cloud_run_client_cls=FakeCloudRunClient,
        ).run()

    assert 'MISSING' in str(error.value)


class FakeOperation(object):
    def __init__(self, response):
        self.response = response

    def result(self):
        return self.response


class FakeCloudRunApiClient(object):
    def __init__(self):
        self.updated = None

    def update_service(self, request):
        self.updated = request['service']
        return FakeOperation({'uri': 'https://checkout.example.run.app', 'latest_ready_revision': 'rev-1'})


def test_cloud_run_client_sends_expected_service_request():
    api_client = FakeCloudRunApiClient()
    result = CloudRunClient('demo-project', 'us-central1', api_client).deploy_service(
        'checkout-api',
        'image-uri',
        ENVIRONMENT_CONFIG,
        FakeSecretsStore.references,
    )

    assert result == {'url': 'https://checkout.example.run.app', 'revision': 'rev-1'}
    assert api_client.updated['name'] == 'projects/demo-project/locations/us-central1/services/checkout-api'
    assert api_client.updated['template']['containers'][0]['image'] == 'image-uri'
    assert api_client.updated['template']['containers'][0]['env'] == FakeSecretsStore.references
    assert api_client.updated['template']['service_account'] == 'run@demo-project.iam.gserviceaccount.com'
