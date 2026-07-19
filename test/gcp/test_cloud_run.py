from types import SimpleNamespace

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.cloud_run import CloudRunServiceUpdater


class FakeSecretStore(object):
    def __init__(self, existing_paths):
        self.existing_paths = existing_paths

    def get_existing_config(self):
        return {}, self.existing_paths


class FakeImageClient(object):
    def __init__(self):
        self.called = False

    def build_and_upload_image(self):
        self.called = True
        return "us-docker.pkg.dev/demo/apps/api:v1"


class FakeCloudRunClient(object):
    def __init__(self):
        self.calls = []

    def deploy_service(self, service, image_uri, env_secret_refs, cloud_run_config):
        self.calls.append((service, image_uri, env_secret_refs, cloud_run_config))
        return SimpleNamespace(uri="https://api.run.app", latest_ready_revision="api-00001")


def test_cloud_run_service_updater_orchestrates_build_secrets_and_deploy(tmpdir):
    env_sample = tmpdir.join("env.sample")
    env_sample.write("PORT=\nDATABASE_URL=\n")
    image_client = FakeImageClient()
    run_client = FakeCloudRunClient()
    config = {
        "project_id": "demo",
        "region": "us-central1",
        "artifact_registry": {"location": "us", "repository": "apps"},
        "cloud_run": {"cpu": "1", "memory": "512Mi", "concurrency": 80, "ingress": "INGRESS_TRAFFIC_ALL"}
    }
    secret_paths = {
        "PORT": "projects/demo/secrets/cloudlift-staging-api-PORT/versions/latest",
        "DATABASE_URL": "projects/demo/secrets/cloudlift-staging-api-DATABASE_URL/versions/latest"
    }

    result = CloudRunServiceUpdater(
        "api", "staging", env_sample_file=str(env_sample), version="v1", config=config,
        secret_store=FakeSecretStore(secret_paths), artifact_registry_client=image_client,
        cloud_run_client=run_client
    ).run()

    assert image_client.called
    assert result.uri == "https://api.run.app"
    assert run_client.calls == [(
        "api",
        "us-docker.pkg.dev/demo/apps/api:v1",
        secret_paths,
        config["cloud_run"]
    )]


def test_cloud_run_service_updater_fails_on_missing_secret(tmpdir):
    env_sample = tmpdir.join("env.sample")
    env_sample.write("PORT=\nDATABASE_URL=\n")
    config = {
        "project_id": "demo",
        "region": "us-central1",
        "artifact_registry": {"location": "us", "repository": "apps"},
        "cloud_run": {}
    }

    with pytest.raises(UnrecoverableException) as exc:
        CloudRunServiceUpdater(
            "api", "staging", env_sample_file=str(env_sample), config=config,
            secret_store=FakeSecretStore({"PORT": "projects/demo/secrets/PORT/versions/latest"}),
            artifact_registry_client=FakeImageClient(), cloud_run_client=FakeCloudRunClient()
        ).run()

    assert "DATABASE_URL" in str(exc.value)
