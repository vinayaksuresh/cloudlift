from click.testing import CliRunner

from cloudlift import cli


def test_gcp_create_environment_command_is_registered_without_aws_preflight(monkeypatch):
    calls = []

    class FakeConfiguration(object):
        def __init__(self, environment):
            self.environment = environment

        def update_config(self):
            calls.append(self.environment)

    def fail_if_aws_client_is_called(service_name):
        raise AssertionError('GCP command should not create an AWS client')

    monkeypatch.setattr('cloudlift.GcpEnvironmentConfiguration', FakeConfiguration)
    monkeypatch.setattr('cloudlift.boto3.client', fail_if_aws_client_is_called)

    result = CliRunner().invoke(cli, ['gcp_create_environment', '-e', 'staging'])

    assert result.exit_code == 0
    assert calls == ['staging']


def test_gcp_deploy_service_command_passes_cli_options(monkeypatch):
    calls = []

    class FakeUpdater(object):
        def __init__(self, name, environment, env_sample_file, version, build_args):
            calls.append({
                'name': name,
                'environment': environment,
                'env_sample_file': env_sample_file,
                'version': version,
                'build_args': build_args
            })

        def run(self):
            calls[-1]['ran'] = True

    monkeypatch.setattr('cloudlift.CloudRunServiceUpdater', FakeUpdater)
    monkeypatch.setattr('cloudlift.boto3.client', lambda service_name: (_ for _ in ()).throw(AssertionError('AWS preflight should not run')))

    result = CliRunner().invoke(cli, [
        'gcp_deploy_service',
        '-e', 'staging',
        '--name', 'api',
        '--version', 'v1',
        '--build-arg', 'SSH_KEY', 'secret'
    ])

    assert result.exit_code == 0
    assert calls == [{
        'name': 'api',
        'environment': 'staging',
        'env_sample_file': None,
        'version': 'v1',
        'build_args': {'SSH_KEY': 'secret'},
        'ran': True
    }]
