from click.testing import CliRunner

from cloudlift import cli


class FakeGcpEnvironmentConfiguration(object):
    created = None

    def __init__(self, environment):
        self.environment = environment

    def create_config(self, **kwargs):
        self.__class__.created = (self.environment, kwargs)

    def get_config(self):
        return {'project_id': 'demo-project'}


class FakeGcpSecretManagerStore(object):
    edited = None

    def __init__(self, name, environment, project_id):
        self.__class__.edited = (name, environment, project_id)

    def edit_config(self):
        self.__class__.edit_called = True


class FakeCloudRunServiceUpdater(object):
    deployed = None

    def __init__(self, name, environment, env_sample_file, version, build_args):
        self.__class__.deployed = (name, environment, env_sample_file, version, build_args)

    def run(self):
        self.__class__.run_called = True


def test_gcp_commands_are_registered_and_invoke_gcp_handlers(monkeypatch):
    monkeypatch.setattr('cloudlift.GcpEnvironmentConfiguration', FakeGcpEnvironmentConfiguration)
    monkeypatch.setattr('cloudlift.GcpSecretManagerStore', FakeGcpSecretManagerStore)
    monkeypatch.setattr('cloudlift.CloudRunServiceUpdater', FakeCloudRunServiceUpdater)
    runner = CliRunner()

    create_result = runner.invoke(cli, [
        'gcp_create_environment',
        '-e', 'staging',
        '--project-id', 'demo-project',
        '--region', 'us-central1',
        '--artifact-registry-repository', 'services',
    ])
    edit_result = runner.invoke(cli, ['gcp_edit_config', '-e', 'staging', '--name', 'checkout-api'])
    deploy_result = runner.invoke(cli, [
        'gcp_deploy_service',
        '-e', 'staging',
        '--name', 'checkout-api',
        '--version', 'v1',
        '--build-arg', 'RAILS_ENV', 'production',
    ])

    assert create_result.exit_code == 0, create_result.output
    assert edit_result.exit_code == 0, edit_result.output
    assert deploy_result.exit_code == 0, deploy_result.output
    assert FakeGcpEnvironmentConfiguration.created[0] == 'staging'
    assert FakeGcpEnvironmentConfiguration.created[1]['artifact_registry_location'] == 'us-central1'
    assert FakeGcpSecretManagerStore.edited == ('checkout-api', 'staging', 'demo-project')
    assert FakeGcpSecretManagerStore.edit_called is True
    assert FakeCloudRunServiceUpdater.deployed == (
        'checkout-api', 'staging', None, 'v1', {'RAILS_ENV': 'production'}
    )
    assert FakeCloudRunServiceUpdater.run_called is True
