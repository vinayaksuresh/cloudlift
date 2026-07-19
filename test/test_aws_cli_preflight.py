from botocore.exceptions import ClientError
from click.testing import CliRunner

import cloudlift
from cloudlift import cli


def test_aws_command_still_runs_aws_preflight(monkeypatch):
    def fail_cloudformation(service):
        assert service == "cloudformation"
        raise ClientError({"Error": {"Code": "AuthFailure", "Message": "no aws"}}, "DescribeStacks")

    monkeypatch.setattr(cloudlift.boto3, "client", fail_cloudformation)

    result = CliRunner().invoke(cli, ["deploy-service", "--name", "api", "-e", "staging"])

    assert result.exit_code == 1
    assert "Could not connect to AWS" in result.output


def test_gcp_command_does_not_run_aws_preflight(monkeypatch):
    called = []

    def fail_if_called(service):
        called.append(service)
        raise AssertionError("AWS preflight should not run for GCP commands")

    class FakeUpdater(object):
        def __init__(self, name, environment, env_sample_file, version, build_args):
            self.name = name
            self.environment = environment

        def run(self):
            return None

    monkeypatch.setattr(cloudlift.boto3, "client", fail_if_called)
    monkeypatch.setattr(cloudlift, "CloudRunServiceUpdater", FakeUpdater)

    result = CliRunner().invoke(cli, ["gcp_deploy_service", "--name", "api", "-e", "staging", "--version", "v1"])

    assert result.exit_code == 0
    assert called == []
