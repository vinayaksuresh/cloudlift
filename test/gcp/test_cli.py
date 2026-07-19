from click.testing import CliRunner

from cloudlift import cli


class FakeGcpEnvironmentConfiguration(object):
    calls = []

    def __init__(self, environment):
        self.environment = environment

    def create_or_update_config(self, **kwargs):
        self.calls.append((self.environment, kwargs))


class FakeCloudRunServiceUpdater(object):
    calls = []

    def __init__(self, name, environment, env_sample_file, version, build_args):
        self.calls.append((name, environment, env_sample_file, version, build_args))

    def run(self):
        return {'url': 'https://api.example.run.app'}


def test_gcp_create_environment_command_is_registered(monkeypatch):
    FakeGcpEnvironmentConfiguration.calls = []
    monkeypatch.setattr('cloudlift.GcpEnvironmentConfiguration', FakeGcpEnvironmentConfiguration)

    result = CliRunner().invoke(cli, [
        'gcp_create_environment',
        '-e', 'staging',
        '--project-id', 'proj',
        '--region', 'us-central1',
        '--artifact-location', 'us',
        '--artifact-repository', 'services',
    ])

    assert result.exit_code == 0
    assert FakeGcpEnvironmentConfiguration.calls[0][0] == 'staging'
    assert FakeGcpEnvironmentConfiguration.calls[0][1]['project_id'] == 'proj'


def test_gcp_deploy_service_command_is_registered(monkeypatch):
    FakeCloudRunServiceUpdater.calls = []
    monkeypatch.setattr('cloudlift.CloudRunServiceUpdater', FakeCloudRunServiceUpdater)

    result = CliRunner().invoke(cli, [
        'gcp_deploy_service',
        '-e', 'staging',
        '--name', 'api',
        '--version', 'v1',
        '--build-arg', 'SSH_KEY', 'secret',
    ])

    assert result.exit_code == 0
    assert FakeCloudRunServiceUpdater.calls == [
        ('api', 'staging', None, 'v1', {'SSH_KEY': 'secret'})
    ]
