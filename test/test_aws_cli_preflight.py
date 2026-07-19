from botocore.exceptions import ClientError
from click.testing import CliRunner

from cloudlift import cli


def aws_connection_error():
    return ClientError({'Error': {'Code': 'AuthFailure', 'Message': 'no aws'}}, 'DescribeStacks')


def test_aws_commands_still_run_aws_preflight(monkeypatch):
    calls = []

    def failing_client(service_name):
        calls.append(service_name)
        raise aws_connection_error()

    monkeypatch.setattr('cloudlift.boto3.client', failing_client)

    result = CliRunner().invoke(cli, ['create_environment', '-e', 'staging'])

    assert result.exit_code == 1
    assert calls == ['cloudformation']
    assert 'Could not connect to AWS!' in result.output


def test_gcp_commands_do_not_require_aws_credentials(monkeypatch):
    calls = []

    class FakeConfiguration(object):
        def __init__(self, environment):
            self.environment = environment

        def update_config(self):
            calls.append(self.environment)

    def failing_client(service_name):
        raise aws_connection_error()

    monkeypatch.setattr('cloudlift.GcpEnvironmentConfiguration', FakeConfiguration)
    monkeypatch.setattr('cloudlift.boto3.client', failing_client)

    result = CliRunner().invoke(cli, ['gcp_create_environment', '-e', 'staging'])

    assert result.exit_code == 0
    assert calls == ['staging']
