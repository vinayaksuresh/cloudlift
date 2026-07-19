import json

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration


def test_create_config_stores_gcp_cloud_run_defaults(tmp_path):
    config_path = tmp_path / 'gcp.json'

    config = GcpEnvironmentConfiguration('staging', str(config_path)).create_config(
        project_id='demo-project',
        region='us-central1',
        artifact_registry_location='us',
        artifact_registry_repository='services',
        service_account='run@demo-project.iam.gserviceaccount.com',
        vpc_connector='projects/demo/locations/us-central1/connectors/main',
    )

    assert config['project_id'] == 'demo-project'
    assert config['artifact_registry'] == {'location': 'us', 'repository': 'services'}
    assert config['cloud_run']['service_defaults']['memory'] == '512Mi'
    assert config['cloud_run']['service_defaults']['concurrency'] == 80
    assert config['cloud_run']['service_account'] == 'run@demo-project.iam.gserviceaccount.com'
    assert json.loads(config_path.read_text())['staging'] == config


def test_get_config_validates_required_gcp_fields(tmp_path):
    config_path = tmp_path / 'gcp.json'
    config_path.write_text(json.dumps({'staging': {'project_id': 'demo-project'}}))

    with pytest.raises(UnrecoverableException) as error:
        GcpEnvironmentConfiguration('staging', str(config_path)).get_config()

    assert 'required property' in str(error.value)


def test_create_config_rejects_invalid_cloud_run_ingress(tmp_path):
    with pytest.raises(UnrecoverableException):
        GcpEnvironmentConfiguration('staging', str(tmp_path / 'gcp.json')).create_config(
            project_id='demo-project',
            region='us-central1',
            artifact_registry_location='us',
            artifact_registry_repository='services',
            ingress='PUBLIC',
        )
