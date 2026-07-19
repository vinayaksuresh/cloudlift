import json
import os

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.providers.gcp.config import GcpEnvironmentConfig


def valid_config():
    return {
        "project_id": "project-1",
        "location": "asia-south1",
        "cluster_name": "cluster-1",
        "namespace": "staging",
        "artifact_registry_repository": "services",
        "service_account": "app-runner",
    }


def test_load_reads_config_from_explicit_path(tmp_path):
    path = tmp_path / "gcp.json"
    path.write_text(json.dumps(valid_config()))

    config = GcpEnvironmentConfig.load("staging", str(path))

    assert config.project_id == "project-1"
    assert config.location == "asia-south1"
    assert config.cluster_name == "cluster-1"
    assert config.namespace == "staging"
    assert config.artifact_registry_repository == "services"
    assert config.service_account == "app-runner"
    assert config.path == str(path)


def test_load_uses_environment_variable_override(tmp_path, monkeypatch):
    path = tmp_path / "override.json"
    path.write_text(json.dumps(valid_config()))
    monkeypatch.setenv("CLOUDLIFT_GCP_CONFIG_PATH", str(path))

    assert GcpEnvironmentConfig.load("staging").path == str(path)


def test_load_or_create_writes_repo_local_config(tmp_path):
    path = tmp_path / ".cloudlift" / "gcp-staging.json"

    config = GcpEnvironmentConfig.load_or_create(
        "staging",
        path=str(path),
        project_id="project-1",
        location="asia-south1",
        cluster_name="cluster-1",
        namespace="apps",
        artifact_registry_repository="services",
    )

    assert config.namespace == "apps"
    assert json.loads(path.read_text()) == {
        "project_id": "project-1",
        "location": "asia-south1",
        "cluster_name": "cluster-1",
        "namespace": "apps",
        "artifact_registry_repository": "services",
    }


def test_missing_required_fields_fail_clearly():
    with pytest.raises(UnrecoverableException) as exc:
        GcpEnvironmentConfig.from_dict("staging", {"project_id": "project-1"})

    assert "location" in exc.value.value
    assert "cluster_name" in exc.value.value
