import subprocess

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient


def test_build_and_upload_image_constructs_artifact_registry_uri(monkeypatch):
    commands = []
    monkeypatch.setattr('cloudlift.gcp.artifact_registry.get_container_tool', lambda: 'docker')
    monkeypatch.setattr('cloudlift.gcp.artifact_registry.subprocess.check_call', lambda command, shell=False: commands.append((command, shell)))

    image_uri = ArtifactRegistryClient(
        'My Service',
        'demo-project',
        'asia-south1',
        'services',
        'v1',
        {'SSH_KEY': 'secret'},
        '.'
    ).build_and_upload_image()

    assert image_uri == 'asia-south1-docker.pkg.dev/demo-project/services/my-service:v1'
    assert commands[0] == ('docker build -t my-service:v1 --build-arg SSH_KEY=secret .', True)
    assert commands[1] == (['docker', 'tag', 'my-service:v1', image_uri], False)
    assert commands[2] == (['gcloud', 'auth', 'configure-docker', 'asia-south1-docker.pkg.dev', '--quiet'], False)
    assert commands[3] == (['docker', 'push', image_uri], False)


def test_build_failure_raises_unrecoverable_exception(monkeypatch):
    monkeypatch.setattr('cloudlift.gcp.artifact_registry.get_container_tool', lambda: 'docker')

    def fail(command, shell=False):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr('cloudlift.gcp.artifact_registry.subprocess.check_call', fail)

    with pytest.raises(UnrecoverableException) as err:
        ArtifactRegistryClient('api', 'demo', 'us', 'repo', 'v1').build_and_upload_image()

    assert 'Unable to build container image' in str(err.value)
