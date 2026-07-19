import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.secrets import GcpSecretManagerStore


class Secret(object):
    def __init__(self, name):
        self.name = name


class Payload(object):
    def __init__(self, data):
        self.data = data


class SecretVersion(object):
    def __init__(self, value):
        self.payload = Payload(value.encode('UTF-8'))


class FakeSecretManagerClient(object):
    def __init__(self):
        self.secrets = {}
        self.deleted = []

    def list_secrets(self, request):
        return [Secret('projects/demo/secrets/' + key) for key in sorted(self.secrets)]

    def access_secret_version(self, request):
        secret_id = request['name'].split('/secrets/')[1].split('/versions/')[0]
        return SecretVersion(self.secrets[secret_id][-1])

    def create_secret(self, request):
        self.secrets.setdefault(request['secret_id'], [])

    def add_secret_version(self, request):
        secret_id = request['parent'].split('/secrets/')[1]
        self.secrets.setdefault(secret_id, []).append(request['payload']['data'].decode('UTF-8'))

    def delete_secret(self, request):
        secret_id = request['name'].split('/secrets/')[1]
        self.deleted.append(secret_id)
        self.secrets.pop(secret_id, None)


def test_secret_store_creates_updates_deletes_and_returns_cloud_run_refs():
    client = FakeSecretManagerClient()
    store = GcpSecretManagerStore('checkout-api', 'staging', 'demo', client)

    store.set_config([('add', '', [('PORT', '8080'), ('API_KEY', 'secret')])])
    store.set_config([('change', 'PORT', ('8080', '9090'))])
    existing, paths = store.get_existing_config()

    assert existing == {'API_KEY': 'secret', 'PORT': '9090'}
    assert paths['PORT'] == 'projects/demo/secrets/cloudlift-staging-checkout-api-PORT/versions/latest'
    assert store.cloud_run_secret_references({'PORT': '', 'API_KEY': ''}) == [
        {
            'name': 'PORT',
            'value_source': {
                'secret_key_ref': {
                    'secret': paths['PORT'],
                    'version': 'latest',
                }
            }
        },
        {
            'name': 'API_KEY',
            'value_source': {
                'secret_key_ref': {
                    'secret': paths['API_KEY'],
                    'version': 'latest',
                }
            }
        },
    ]

    store.set_config([('remove', '', [('API_KEY', 'secret')])])

    assert 'cloudlift-staging-checkout-api-API_KEY' in client.deleted
    assert 'API_KEY' not in store.get_existing_config()[0]


def test_secret_store_rejects_keys_that_are_not_cloud_run_env_vars():
    store = GcpSecretManagerStore('checkout-api', 'staging', 'demo', FakeSecretManagerClient())

    with pytest.raises(UnrecoverableException):
        store.set_config([('add', '', [('1INVALID', 'value')])])
