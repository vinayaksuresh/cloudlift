from types import SimpleNamespace

import pytest

from cloudlift.exceptions import UnrecoverableException
from cloudlift.gcp.secrets import GcpSecretManagerStore


class FakeSecretManagerClient(object):
    def __init__(self):
        self.secrets = {}
        self.deleted = []

    def list_secrets(self, request):
        for secret_id in self.secrets:
            yield SimpleNamespace(name="%s/secrets/%s" % (request["parent"], secret_id))

    def access_secret_version(self, request):
        secret_id = request["name"].split("/secrets/")[1].split("/")[0]
        return SimpleNamespace(payload=SimpleNamespace(data=self.secrets[secret_id].encode("UTF-8")))

    def create_secret(self, request):
        self.secrets[request["secret_id"]] = ""

    def add_secret_version(self, request):
        secret_id = request["parent"].split("/secrets/")[1]
        self.secrets[secret_id] = request["payload"]["data"].decode("UTF-8")

    def delete_secret(self, request):
        self.deleted.append(request["name"])
        self.secrets.pop(request["name"].split("/secrets/")[1], None)


def test_secret_store_validates_keys_and_returns_cloud_run_references():
    client = FakeSecretManagerClient()
    store = GcpSecretManagerStore("api", "staging", "demo", client=client)

    refs = store.secret_references_for_keys(["DATABASE_URL"])

    assert refs["DATABASE_URL"] == "projects/demo/secrets/cloudlift-staging-api-DATABASE_URL/versions/latest"
    assert store._is_a_valid_parameter_key("DATABASE_URL")
    assert not store._is_a_valid_parameter_key("1_BAD")
    assert not store._is_a_valid_parameter_key("BAD-KEY")


def test_secret_store_create_update_delete_with_mocked_client():
    client = FakeSecretManagerClient()
    store = GcpSecretManagerStore("api", "staging", "demo", client=client)

    store.set_config([("add", "", [("PORT", "8080"), ("DATABASE_URL", "postgres")])])
    store.set_config([("change", "PORT", ("8080", "9090"))])
    existing, refs = store.get_existing_config()

    assert existing["PORT"] == "9090"
    assert existing["DATABASE_URL"] == "postgres"
    assert refs["PORT"].endswith("/cloudlift-staging-api-PORT/versions/latest")

    store.set_config([("remove", "", [("DATABASE_URL", "postgres")])])
    assert "DATABASE_URL" not in store.get_existing_config()[0]
    assert client.deleted == ["projects/demo/secrets/cloudlift-staging-api-DATABASE_URL"]


def test_secret_store_rejects_invalid_changes():
    store = GcpSecretManagerStore("api", "staging", "demo", client=FakeSecretManagerClient())

    with pytest.raises(UnrecoverableException):
        store.set_config([("add", "", [("BAD-KEY", "value")])])
