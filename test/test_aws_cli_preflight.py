from botocore.exceptions import NoCredentialsError
from click.testing import CliRunner

from cloudlift import cli


class FakeCloudRunServiceUpdater(object):
    called = False

    def __init__(self, name, environment, env_sample_file, version, build_args):
        self.name = name
        self.environment = environment

    def run(self):
        FakeCloudRunServiceUpdater.called = True
        return {}


def test_gcp_commands_do_not_require_aws_credentials(monkeypatch):
    FakeCloudRunServiceUpdater.called = False
    monkeypatch.setattr('cloudlift.CloudRunServiceUpdater', FakeCloudRunServiceUpdater)

    def fail_if_called(service_name):
        raise AssertionError('AWS client should not be created for GCP commands')

    monkeypatch.setattr('cloudlift.boto3.client', fail_if_called)

    result = CliRunner().invoke(cli, [
        'gcp_deploy_service', '-e', 'staging', '--name', 'api', '--version', 'v1'
    ])

    assert result.exit_code == 0
    assert FakeCloudRunServiceUpdater.called


def test_aws_commands_still_require_aws_credentials(monkeypatch):
    monkeypatch.setattr(
        'cloudlift.boto3.client',
        lambda service_name: (_ for _ in ()).throw(NoCredentialsError()),
    )

    result = CliRunner().invoke(cli, [
        'deploy_service', '-e', 'staging', '--name', 'api', '--version', 'v1'
    ])

    assert result.exit_code == 1
    assert 'Could not connect to AWS!' in result.output
