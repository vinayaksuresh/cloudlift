import subprocess

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient


def test_artifact_registry_builds_expected_image_uri_and_commands(monkeypatch):
    calls = []

    def fake_check_call(command, shell=False):
        calls.append((command, shell))

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    client = ArtifactRegistryClient(
        "My API", "demo", "us-central1", "apps", version="v1",
        build_args={"SSH_KEY": "secret", "A": "1"}, container_tool="docker"
    )

    image_uri = client.build_and_upload_image()

    assert image_uri == "us-central1-docker.pkg.dev/demo/apps/my-api:v1"
    assert calls[0] == ("docker build -t my-api:v1 --build-arg SSH_KEY=secret --build-arg A=1 .", True)
    assert calls[1] == (["docker", "tag", "my-api:v1", image_uri], False)
    assert calls[2] == (["gcloud", "auth", "configure-docker", "us-central1-docker.pkg.dev", "--quiet"], False)
    assert calls[3] == (["docker", "push", image_uri], False)


def test_artifact_registry_raises_unrecoverable_on_subprocess_failure(monkeypatch):
    def fake_check_call(command, shell=False):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "check_call", fake_check_call)
    client = ArtifactRegistryClient("api", "demo", "us", "apps", version="v1", container_tool="docker")

    with pytest.raises(UnrecoverableException) as exc:
        client.build_and_upload_image()

    assert "build failed" in str(exc.value).lower()
