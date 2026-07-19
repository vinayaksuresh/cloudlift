from types import SimpleNamespace

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.secrets import GcpSecretManagerStore


class FakeSecretManagerClient(object):
    def __init__(self):
        self.created = []
        self.added_versions = []
        self.deleted = []
        self.secrets = []
        self.values = {}

    def list_secrets(self, request):
        self.list_parent = request['parent']
        return self.secrets

    def access_secret_version(self, request):
        return SimpleNamespace(payload=SimpleNamespace(data=self.values[request['name']].encode('UTF-8')))

    def create_secret(self, request):
        self.created.append(request)

    def add_secret_version(self, request):
        self.added_versions.append(request)

    def delete_secret(self, request):
        self.deleted.append(request)


def test_get_existing_config_returns_secret_values_and_cloud_run_references():
    client = FakeSecretManagerClient()
    secret_name = 'projects/demo/secrets/cloudlift-staging-api-PORT'
    client.secrets = [
        SimpleNamespace(name=secret_name, labels={
            'cloudlift_environment': 'staging',
            'cloudlift_service': 'api',
            'cloudlift_key': 'PORT'
        }),
        SimpleNamespace(name='projects/demo/secrets/other', labels={
            'cloudlift_environment': 'prod',
            'cloudlift_service': 'api',
            'cloudlift_key': 'PORT'
        })
    ]
    client.values[secret_name + '/versions/latest'] = '8080'

    values, references = GcpSecretManagerStore('api', 'staging', 'demo', client).get_existing_config()

    assert values == {'PORT': '8080'}
    assert references == {'PORT': 'projects/demo/secrets/cloudlift-staging-api-PORT:latest'}
    assert client.list_parent == 'projects/demo'


def test_set_config_creates_updates_and_deletes_secret_versions():
    client = FakeSecretManagerClient()
    store = GcpSecretManagerStore('api', 'staging', 'demo', client)

    store.set_config([
        ['change', 'PORT', ('8080', '9090')],
        ['add', '', [('LABEL', 'Demo')]],
        ['remove', '', [('OLD_KEY', 'unused')]]
    ])

    assert client.created[0]['secret_id'] == 'cloudlift-staging-api-LABEL'
    assert client.created[0]['secret']['labels']['cloudlift_key'] == 'LABEL'
    assert client.added_versions == [
        {
            'parent': 'projects/demo/secrets/cloudlift-staging-api-PORT',
            'payload': {'data': b'9090'}
        },
        {
            'parent': 'projects/demo/secrets/cloudlift-staging-api-LABEL',
            'payload': {'data': b'Demo'}
        }
    ]
    assert client.deleted == [{'name': 'projects/demo/secrets/cloudlift-staging-api-OLD_KEY'}]


def test_invalid_secret_keys_are_rejected():
    store = GcpSecretManagerStore('api', 'staging', 'demo', FakeSecretManagerClient())

    with pytest.raises(UnrecoverableException):
        store.set_config([['add', '', [('BAD-KEY', 'value')]]])
