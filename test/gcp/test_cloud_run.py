from types import SimpleNamespace

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.cloud_run import CloudRunClient, CloudRunServiceUpdater


CONFIG = {
    'project_id': 'demo-project',
    'region': 'asia-south1',
    'artifact_registry': {
        'location': 'asia-south1',
        'repository': 'services'
    },
    'service_defaults': {
        'cpu': '1',
        'memory': '512Mi',
        'concurrency': 10,
        'service_account': 'runner@demo-project.iam.gserviceaccount.com',
        'vpc_connector': 'projects/demo/locations/asia-south1/connectors/private',
        'ingress': 'INGRESS_TRAFFIC_ALL'
    }
}


class FakeConfiguration(object):
    def __init__(self, environment):
        self.environment = environment

    def get_config(self):
        return CONFIG


class FakeSecrets(object):
    def __init__(self, name, environment, project_id):
        self.name = name
        self.environment = environment
        self.project_id = project_id

    def get_existing_config(self):
        return {}, {
            'PORT': 'projects/demo-project/secrets/cloudlift-staging-api-PORT:latest',
            'LABEL': 'projects/demo-project/secrets/cloudlift-staging-api-LABEL:latest'
        }


class FakeImageClient(object):
    calls = []

    def __init__(self, *args):
        FakeImageClient.calls.append(args)

    def build_and_upload_image(self):
        return 'asia-south1-docker.pkg.dev/demo-project/services/api:v1'


class FakeCloudRunClient(object):
    calls = []

    def __init__(self, project_id, region):
        self.project_id = project_id
        self.region = region

    def deploy_service(self, service_name, image_uri, secret_references, service_defaults):
        FakeCloudRunClient.calls.append({
            'project_id': self.project_id,
            'region': self.region,
            'service_name': service_name,
            'image_uri': image_uri,
            'secret_references': secret_references,
            'service_defaults': service_defaults
        })
        return {'url': 'https://api.example.run.app', 'revision': 'api-00001'}


def test_cloud_run_service_updater_builds_pushes_and_deploys_with_secret_refs(tmp_path):
    FakeImageClient.calls = []
    FakeCloudRunClient.calls = []
    env_sample = tmp_path / 'env.sample'
    env_sample.write_text('PORT=\nLABEL=\n')

    result = CloudRunServiceUpdater(
        'api',
        'staging',
        str(env_sample),
        'v1',
        {'SSH_KEY': 'secret'},
        '.',
        FakeConfiguration,
        FakeSecrets,
        FakeImageClient,
        FakeCloudRunClient
    ).run()

    assert result == {'url': 'https://api.example.run.app', 'revision': 'api-00001'}
    assert FakeImageClient.calls[0] == ('api', 'demo-project', 'asia-south1', 'services', 'v1', {'SSH_KEY': 'secret'}, '.')
    assert FakeCloudRunClient.calls[0]['project_id'] == 'demo-project'
    assert FakeCloudRunClient.calls[0]['region'] == 'asia-south1'
    assert FakeCloudRunClient.calls[0]['service_name'] == 'api'
    assert FakeCloudRunClient.calls[0]['secret_references'] == {
        'PORT': 'projects/demo-project/secrets/cloudlift-staging-api-PORT:latest',
        'LABEL': 'projects/demo-project/secrets/cloudlift-staging-api-LABEL:latest'
    }


def test_cloud_run_service_updater_fails_when_env_sample_secret_is_missing(tmp_path):
    class MissingSecretStore(FakeSecrets):
        def get_existing_config(self):
            return {}, {'PORT': 'projects/demo/secrets/PORT:latest'}

    env_sample = tmp_path / 'env.sample'
    env_sample.write_text('PORT=\nLABEL=\n')

    with pytest.raises(UnrecoverableException) as err:
        CloudRunServiceUpdater(
            'api', 'staging', str(env_sample), 'v1', {}, '.',
            FakeConfiguration, MissingSecretStore, FakeImageClient, FakeCloudRunClient
        ).run()

    assert 'LABEL' in str(err.value)


def test_cloud_run_client_builds_cloud_run_secret_environment_payload():
    class Operation(object):
        def result(self):
            return SimpleNamespace(uri='https://api.example.run.app', latest_ready_revision='api-00001')

    class FakeServicesClient(object):
        def __init__(self):
            self.created = None

        def get_service(self, request):
            raise Exception('not found')

        def create_service(self, request):
            self.created = request
            return Operation()

    fake = FakeServicesClient()
    result = CloudRunClient('demo-project', 'asia-south1', fake).deploy_service(
        'api',
        'image-uri',
        {'PORT': 'projects/demo-project/secrets/PORT:latest'},
        {'cpu': '1', 'memory': '512Mi', 'concurrency': 10, 'ingress': 'INGRESS_TRAFFIC_ALL'}
    )

    service = fake.created['service']
    assert fake.created['parent'] == 'projects/demo-project/locations/asia-south1'
    assert service['template']['containers'][0]['image'] == 'image-uri'
    assert service['template']['containers'][0]['env'][0]['value_source']['secret_key_ref'] == {
        'secret': 'projects/demo-project/secrets/PORT',
        'version': 'latest'
    }
    assert result['url'] == 'https://api.example.run.app'
