from click.testing import CliRunner

import cloudlift
from cloudlift import cli


class FakeGcpEnvironmentConfiguration(object):
    called = False

    def __init__(self, environment):
        self.environment = environment

    def update_config(self):
        FakeGcpEnvironmentConfiguration.called = self.environment


def test_gcp_commands_are_registered_with_underscore_names():
    assert "gcp_create_environment" in cli.commands
    assert "gcp_edit_config" in cli.commands
    assert "gcp_deploy_service" in cli.commands


def test_gcp_create_environment_does_not_require_aws_credentials(monkeypatch):
    def fail_if_called(service):
        raise AssertionError("AWS preflight should not run for GCP commands")

    monkeypatch.setattr(cloudlift.boto3, "client", fail_if_called)
    monkeypatch.setattr(cloudlift, "GcpEnvironmentConfiguration", FakeGcpEnvironmentConfiguration)

    result = CliRunner().invoke(cli, ["gcp_create_environment", "-e", "staging"])

    assert result.exit_code == 0
    assert FakeGcpEnvironmentConfiguration.called == "staging"
