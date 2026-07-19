from botocore.exceptions import ClientError
from click.testing import CliRunner

from cloudlift import cli


class FakeGcpEnvironmentConfiguration(object):
    def __init__(self, environment):
        self.environment = environment

    def create_config(self, **kwargs):
        self.kwargs = kwargs


def test_gcp_command_does_not_require_aws_credentials(monkeypatch):
    def fail_if_aws_client_requested(service_name):
        raise AssertionError('GCP command should not create AWS clients')

    monkeypatch.setattr('cloudlift.boto3.client', fail_if_aws_client_requested)
    monkeypatch.setattr('cloudlift.GcpEnvironmentConfiguration', FakeGcpEnvironmentConfiguration)

    result = CliRunner().invoke(cli, [
        'gcp_create_environment',
        '-e', 'staging',
        '--project-id', 'demo-project',
        '--region', 'us-central1',
        '--artifact-registry-repository', 'services',
    ])

    assert result.exit_code == 0, result.output


def test_aws_command_still_requires_aws_credentials(monkeypatch):
    def raise_client_error(service_name):
        raise ClientError({'Error': {'Code': 'AuthFailure', 'Message': 'no credentials'}}, 'CreateClient')

    monkeypatch.setattr('cloudlift.boto3.client', raise_client_error)
    result = CliRunner().invoke(cli, ['create_environment', '-e', 'staging'])

    assert result.exit_code == 1
    assert 'Could not connect to AWS!' in result.output
