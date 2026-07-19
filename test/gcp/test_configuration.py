import json

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration


def test_gcp_environment_configuration_writes_gcp_only_shape(tmp_path):
    config_path = tmp_path / 'gcp.json'
    configuration = GcpEnvironmentConfiguration('staging', config_path=str(config_path))

    configuration.create_or_update_config(
        project_id='my-project',
        region='us-central1',
        artifact_registry_location='us',
        artifact_registry_repository='services',
        service_account='runner@my-project.iam.gserviceaccount.com',
        vpc_connector='projects/my-project/locations/us-central1/connectors/default',
    )

    saved = json.loads(config_path.read_text())
    env_config = saved['environments']['staging']
    assert env_config == configuration.get_config()
    assert env_config['project_id'] == 'my-project'
    assert env_config['artifact_registry'] == {
        'location': 'us',
        'repository': 'services',
    }
    assert env_config['service_defaults']['concurrency'] == 80
    assert env_config['service_defaults']['ingress'] == 'INGRESS_TRAFFIC_ALL'
    assert 'vpc' not in env_config
    assert 'cluster' not in env_config


def test_gcp_environment_configuration_validates_required_fields(tmp_path):
    config_path = tmp_path / 'gcp.json'
    configuration = GcpEnvironmentConfiguration('staging', config_path=str(config_path))

    with pytest.raises(UnrecoverableException) as exc:
        configuration._set_config({'environments': {'staging': {'region': 'us-central1'}}})

    assert 'project_id' in str(exc.value)
