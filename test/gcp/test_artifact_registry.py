import subprocess

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient


def test_artifact_registry_client_builds_expected_image_uri_and_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'check_call', lambda command: calls.append(command))
    client = ArtifactRegistryClient(
        'My API',
        'proj',
        'us',
        'services',
        version='v1',
        build_args={'SSH_KEY': 'secret'},
        working_dir='/app',
        container_tool='docker',
    )

    image_uri = client.build_and_upload_image()

    assert image_uri == 'us-docker.pkg.dev/proj/services/my-api:v1'
    assert calls == [
        ['docker', 'build', '-t', 'my-api:v1', '--build-arg', 'SSH_KEY=secret', '/app'],
        ['docker', 'tag', 'my-api:v1', 'us-docker.pkg.dev/proj/services/my-api:v1'],
        ['gcloud', 'auth', 'configure-docker', 'us-docker.pkg.dev', '--quiet'],
        ['docker', 'push', 'us-docker.pkg.dev/proj/services/my-api:v1'],
        ['docker', 'rmi', 'us-docker.pkg.dev/proj/services/my-api:v1'],
    ]


def test_artifact_registry_client_raises_unrecoverable_on_subprocess_failure(monkeypatch):
    def fail(command):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, 'check_call', fail)
    client = ArtifactRegistryClient(
        'api', 'proj', 'us', 'services', version='v1', container_tool='docker'
    )

    with pytest.raises(UnrecoverableException):
        client.build_and_upload_image()
