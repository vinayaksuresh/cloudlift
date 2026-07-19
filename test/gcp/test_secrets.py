from types import SimpleNamespace

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.secrets import GcpSecretManagerStore


class FakeSecretManagerClient(object):
    def __init__(self):
        self.secrets = {
            'projects/proj/secrets/cloudlift-staging-api-db-url': b'postgres://example',
            'projects/proj/secrets/other-secret': b'ignored',
        }
        self.created = []
        self.added_versions = []
        self.deleted = []

    def list_secrets(self, request):
        assert request == {'parent': 'projects/proj'}
        return [SimpleNamespace(name=name) for name in sorted(self.secrets)]

    def access_secret_version(self, request):
        secret_name = request['name'].replace('/versions/latest', '')
        return SimpleNamespace(payload=SimpleNamespace(data=self.secrets[secret_name]))

    def get_secret(self, request):
        if request['name'] not in self.secrets:
            raise Exception('not found')
        return SimpleNamespace(name=request['name'])

    def create_secret(self, request):
        name = request['parent'] + '/secrets/' + request['secret_id']
        self.created.append(request)
        self.secrets[name] = b''
        return SimpleNamespace(name=name)

    def add_secret_version(self, request):
        self.added_versions.append(request)
        self.secrets[request['parent']] = request['payload']['data']

    def delete_secret(self, request):
        self.deleted.append(request['name'])
        self.secrets.pop(request['name'], None)


def test_secret_manager_store_lists_values_and_cloud_run_references():
    store = GcpSecretManagerStore('api', 'staging', 'proj', client=FakeSecretManagerClient())

    values, references = store.get_existing_config()

    assert values == {'DB_URL': 'postgres://example'}
    assert references == {
        'DB_URL': {
            'secret': 'projects/proj/secrets/cloudlift-staging-api-db-url',
            'version': 'latest',
        }
    }


def test_secret_manager_store_creates_updates_and_deletes_changed_keys():
    client = FakeSecretManagerClient()
    store = GcpSecretManagerStore('api', 'staging', 'proj', client=client)

    store.set_config([
        ('change', 'DB_URL', ('old', 'new')),
        ('add', '', [('TOKEN', 'abc')]),
        ('remove', '', [('OLD_KEY', 'unused')]),
    ])

    assert client.secrets['projects/proj/secrets/cloudlift-staging-api-db-url'] == b'new'
    assert client.secrets['projects/proj/secrets/cloudlift-staging-api-token'] == b'abc'
    assert client.created[0]['secret_id'] == 'cloudlift-staging-api-token'
    assert 'projects/proj/secrets/cloudlift-staging-api-old-key' in client.deleted


def test_secret_manager_store_rejects_invalid_env_keys():
    store = GcpSecretManagerStore('api', 'staging', 'proj', client=FakeSecretManagerClient())

    with pytest.raises(UnrecoverableException):
        store.set_config([('add', '', [('DATABASE-URL', 'bad')])])
