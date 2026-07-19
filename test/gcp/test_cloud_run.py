from types import SimpleNamespace

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.cloud_run import CloudRunClient, CloudRunServiceUpdater


class FakeArtifactRegistryClient(object):
    def __init__(self):
        self.called = False

    def build_and_upload_image(self):
        self.called = True
        return 'us-docker.pkg.dev/proj/services/api:v1'


class FakeSecretStore(object):
    def __init__(self, values, refs):
        self.values = values
        self.refs = refs

    def get_existing_config(self):
        return self.values, self.refs


class FakeCloudRunDeployClient(object):
    def __init__(self):
        self.calls = []

    def deploy_service(self, service_name, image_uri, secret_env_vars, service_defaults):
        self.calls.append((service_name, image_uri, secret_env_vars, service_defaults))
        return {'url': 'https://api.example.run.app', 'revision': 'api-00001'}


def test_cloud_run_service_updater_orchestrates_build_secrets_and_deploy(tmp_path):
    env_sample = tmp_path / 'env.sample'
    env_sample.write_text('DB_URL=\nTOKEN=\n')
    artifact_client = FakeArtifactRegistryClient()
    cloud_run_client = FakeCloudRunDeployClient()
    secret_refs = {
        'DB_URL': {'secret': 'projects/proj/secrets/db-url', 'version': 'latest'},
        'TOKEN': {'secret': 'projects/proj/secrets/token', 'version': 'latest'},
    }

    deployment = CloudRunServiceUpdater(
        'api',
        'staging',
        env_sample_file=str(env_sample),
        config={
            'project_id': 'proj',
            'region': 'us-central1',
            'artifact_registry': {'location': 'us', 'repository': 'services'},
            'service_defaults': {'cpu': '1000m', 'memory': '512Mi', 'concurrency': 10},
        },
        secret_store=FakeSecretStore({'DB_URL': 'db', 'TOKEN': 'token'}, secret_refs),
        artifact_registry_client=artifact_client,
        cloud_run_client=cloud_run_client,
    ).run()

    assert artifact_client.called
    assert deployment['url'] == 'https://api.example.run.app'
    assert cloud_run_client.calls == [(
        'api',
        'us-docker.pkg.dev/proj/services/api:v1',
        secret_refs,
        {'cpu': '1000m', 'memory': '512Mi', 'concurrency': 10},
    )]


def test_cloud_run_service_updater_fails_when_secret_missing(tmp_path):
    env_sample = tmp_path / 'env.sample'
    env_sample.write_text('DB_URL=\nTOKEN=\n')

    with pytest.raises(UnrecoverableException) as exc:
        CloudRunServiceUpdater(
            'api',
            'staging',
            env_sample_file=str(env_sample),
            config={
                'project_id': 'proj',
                'region': 'us-central1',
                'artifact_registry': {'location': 'us', 'repository': 'services'},
            },
            secret_store=FakeSecretStore(
                {'DB_URL': 'db'},
                {'DB_URL': {'secret': 'projects/proj/secrets/db-url', 'version': 'latest'}},
            ),
            artifact_registry_client=FakeArtifactRegistryClient(),
            cloud_run_client=FakeCloudRunDeployClient(),
        ).run()

    assert 'TOKEN' in str(exc.value)


class FakeOperation(object):
    def result(self):
        return SimpleNamespace(
            name='projects/proj/locations/us-central1/services/api',
            uri='https://api.example.run.app',
            latest_ready_revision='api-00001',
        )


class FakeServicesClient(object):
    def __init__(self):
        self.created = None

    def get_service(self, request):
        raise Exception('not found')

    def create_service(self, request):
        self.created = request
        return FakeOperation()


def test_cloud_run_client_creates_service_with_secret_manager_env_vars():
    fake_client = FakeServicesClient()
    client = CloudRunClient('proj', 'us-central1', client=fake_client)

    result = client.deploy_service(
        'api',
        'us-docker.pkg.dev/proj/services/api:v1',
        {'DB_URL': {'secret': 'projects/proj/secrets/db-url', 'version': 'latest'}},
        {'cpu': '1000m', 'memory': '512Mi', 'concurrency': 5, 'ingress': 'INGRESS_TRAFFIC_ALL'},
    )

    assert result['revision'] == 'api-00001'
    service = fake_client.created['service']
    assert fake_client.created['parent'] == 'projects/proj/locations/us-central1'
    assert fake_client.created['service_id'] == 'api'
    assert service['template']['containers'][0]['env'] == [{
        'name': 'DB_URL',
        'value_source': {
            'secret_key_ref': {
                'secret': 'projects/proj/secrets/db-url',
                'version': 'latest',
            }
        },
    }]
