from click.testing import CliRunner

import cloudlift
from cloudlift.providers.aws import AwsProvider
from cloudlift.providers.gcp.provider import GcpProvider


class RecordingProvider(object):
    def __init__(self):
        self.calls = []

    def create_service(self, *args, **kwargs):
        self.calls.append(("create_service", args, kwargs))

    def create_environment(self, *args, **kwargs):
        self.calls.append(("create_environment", args, kwargs))

    def deploy_service(self, *args, **kwargs):
        self.calls.append(("deploy_service", args, kwargs))

    def create_task_definition(self, *args, **kwargs):
        self.calls.append(("create_task_definition", args, kwargs))


def test_provider_factory_returns_aws_by_default_and_gcp_when_requested():
    from cloudlift.providers import get_provider

    assert isinstance(get_provider("aws"), AwsProvider)
    assert isinstance(get_provider("gcp"), GcpProvider)


def test_gcp_command_routes_to_gcp_provider_without_aws_preamble(monkeypatch):
    provider = RecordingProvider()
    monkeypatch.setattr(cloudlift, "get_provider", lambda name: provider)
    monkeypatch.setattr(
        cloudlift,
        "highlight_user_account_details",
        lambda: (_ for _ in ()).throw(AssertionError("AWS preamble should not run for GCP")),
    )

    result = CliRunner().invoke(
        cloudlift.cli,
        [
            "create_service",
            "--provider",
            "gcp",
            "--name",
            "orders",
            "-e",
            "staging",
            "--config-path",
            "gcp.json",
            "--container-port",
            "8080",
            "--replicas",
            "3",
            "--version",
            "abc123",
        ],
    )

    assert result.exit_code == 0, result.output
    assert provider.calls == [
        (
            "create_service",
            ("orders", "staging"),
            {
                "config_path": "gcp.json",
                "container_port": 8080,
                "replicas": 3,
                "version": "abc123",
            },
        )
    ]


def test_aws_is_default_provider_for_existing_commands(monkeypatch):
    provider = RecordingProvider()
    seen_providers = []
    monkeypatch.setattr(cloudlift, "get_provider", lambda name: seen_providers.append(name) or provider)
    monkeypatch.setattr(cloudlift, "highlight_user_account_details", lambda: None)

    result = CliRunner().invoke(
        cloudlift.cli,
        ["deploy_service", "--name", "orders", "-e", "staging", "--version", "abc123"],
    )

    assert result.exit_code == 0, result.output
    assert seen_providers == ["aws"]
    assert provider.calls[0][0] == "deploy_service"
    assert provider.calls[0][1] == ("orders", "staging")
    assert provider.calls[0][2]["version"] == "abc123"


def test_gcp_task_definition_fails_explicitly(monkeypatch):
    class UnsupportedProvider(RecordingProvider):
        def create_task_definition(self, *args, **kwargs):
            from cloudlift.exceptions import UnrecoverableException
            raise UnrecoverableException("GCP provider does not support ECS task definitions")

    monkeypatch.setattr(cloudlift, "get_provider", lambda name: UnsupportedProvider())

    result = CliRunner().invoke(
        cloudlift.cli,
        [
            "create_task_definition",
            "--provider",
            "gcp",
            "--name",
            "orders",
            "-e",
            "staging",
        ],
    )

    assert result.exit_code == 1
    assert "GCP provider does not support ECS task definitions" in result.output
