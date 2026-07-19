import json

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration


def test_gcp_environment_configuration_validates_and_persists(tmpdir):
    config = GcpEnvironmentConfiguration("staging", config_dir=str(tmpdir))
    data = config.default_config()
    data["project_id"] = "demo-project"

    config._set_config(data)

    assert config.get_config()["project_id"] == "demo-project"
    assert json.load(open(config.config_path))["artifact_registry"]["repository"] == "cloudlift"


def test_gcp_environment_configuration_rejects_aws_shaped_config(tmpdir):
    config = GcpEnvironmentConfiguration("staging", config_dir=str(tmpdir))

    with pytest.raises(UnrecoverableException) as exc:
        config._validate_config({"staging": {"region": "ap-south-1", "vpc": {}}})

    assert "project_id" in str(exc.value)


def test_gcp_environment_configuration_requires_existing_file(tmpdir):
    config = GcpEnvironmentConfiguration("missing", config_dir=str(tmpdir))

    with pytest.raises(UnrecoverableException):
        config.get_config()
