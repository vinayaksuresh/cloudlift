import json

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.configuration import GcpEnvironmentConfiguration


def test_get_config_reads_gcp_environment_from_local_json(tmp_path):
    config_file = tmp_path / 'gcp.json'
    config = {
        'staging': {
            'project_id': 'demo-project',
            'region': 'asia-south1',
            'artifact_registry': {
                'location': 'asia-south1',
                'repository': 'services'
            },
            'service_defaults': {
                'cpu': '1',
                'memory': '512Mi',
                'concurrency': 80,
                'ingress': 'INGRESS_TRAFFIC_ALL'
            }
        }
    }
    config_file.write_text(json.dumps(config))

    assert GcpEnvironmentConfiguration('staging', str(config_file)).get_config() == config['staging']


def test_set_config_validates_only_gcp_relevant_fields(tmp_path):
    config_file = tmp_path / 'gcp.json'
    config = {
        'project_id': 'demo-project',
        'region': 'asia-south1',
        'artifact_registry': {
            'location': 'asia-south1',
            'repository': 'services'
        },
        'service_defaults': {
            'cpu': '2',
            'memory': '1Gi',
            'concurrency': 20,
            'service_account': 'svc@demo-project.iam.gserviceaccount.com',
            'vpc_connector': '',
            'ingress': 'INGRESS_TRAFFIC_ALL'
        }
    }

    GcpEnvironmentConfiguration('staging', str(config_file)).set_config(config)

    stored = json.loads(config_file.read_text())
    assert stored == {'staging': config}
    assert 'vpc' not in stored['staging']
    assert 'cluster' not in stored['staging']


def test_invalid_ingress_is_rejected(tmp_path):
    config = GcpEnvironmentConfiguration('staging', str(tmp_path / 'gcp.json'))

    with pytest.raises(UnrecoverableException) as err:
        config.set_config({
            'project_id': 'demo-project',
            'region': 'asia-south1',
            'artifact_registry': {
                'location': 'asia-south1',
                'repository': 'services'
            },
            'service_defaults': {
                'concurrency': 80,
                'ingress': 'public'
            }
        })

    assert 'service_defaults.ingress' in str(err.value)
