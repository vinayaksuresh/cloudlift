import subprocess

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.artifact_registry import ArtifactRegistryClient


def test_artifact_registry_builds_tags_and_pushes_image(monkeypatch):
    calls = []

    def fake_check_call(command, shell=False):
        calls.append((command, shell))

    monkeypatch.setattr(subprocess, 'check_call', fake_check_call)

    client = ArtifactRegistryClient(
        'checkout-api',
        'demo-project',
        'us-central1',
        'services',
        build_args={'RAILS_ENV': 'production'},
        container_tool='docker',
    )

    image_uri = client.build_and_upload_image('v1')

    assert image_uri == 'us-central1-docker.pkg.dev/demo-project/services/checkout-api:v1'
    assert calls[0] == ('docker build -t checkout-api:v1 --build-arg RAILS_ENV=production .', True)
    assert calls[1] == (['docker', 'tag', 'checkout-api:v1', image_uri], False)
    assert calls[2] == (['gcloud', 'auth', 'configure-docker', 'us-central1-docker.pkg.dev', '--quiet'], False)
    assert calls[3] == (['docker', 'push', image_uri], False)


def test_artifact_registry_raises_unrecoverable_on_subprocess_failure(monkeypatch):
    def fake_check_call(command, shell=False):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, 'check_call', fake_check_call)
    client = ArtifactRegistryClient('checkout-api', 'demo', 'us', 'services', container_tool='docker')

    with pytest.raises(UnrecoverableException):
        client.build_and_upload_image('v1')
