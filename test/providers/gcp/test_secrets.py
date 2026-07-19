from cloudlift.providers.gcp.config import GcpEnvironmentConfig
from cloudlift.providers.gcp.secrets import SecretManagerConfigStore


class Payload(object):
    def __init__(self, data):
        self.data = data


class Response(object):
    def __init__(self, data):
        self.payload = Payload(data)


class FakeSecretManagerClient(object):
    def __init__(self):
        self.secrets = set()
        self.versions = {}
        self.created = []

    def secret_path(self, project_id, secret_id):
        return "projects/{}/secrets/{}".format(project_id, secret_id)

    def get_secret(self, request):
        if request["name"] not in self.secrets:
            raise Exception("not found")
        return request["name"]

    def create_secret(self, request):
        path = "{}/secrets/{}".format(request["parent"], request["secret_id"])
        self.secrets.add(path)
        self.created.append(request)
        return path

    def add_secret_version(self, request):
        self.versions[request["parent"]] = request["payload"]["data"]
        return request

    def access_secret_version(self, request):
        parent = request["name"].rsplit("/versions/", 1)[0]
        return Response(self.versions[parent])


def config():
    return GcpEnvironmentConfig(
        environment="staging",
        project_id="project-1",
        location="asia-south1",
        cluster_name="cluster-1",
        namespace="apps",
        artifact_registry_repository="services",
    )


def test_secret_ids_are_predictable_and_safe():
    store = SecretManagerConfigStore(config(), FakeSecretManagerClient())

    assert store.secret_id("orders-api", "DATABASE_URL") == "cloudlift-staging-orders-api-DATABASE_URL"
    assert store.secret_id("orders api", "API.KEY") == "cloudlift-staging-orders-api-API-KEY"


def test_write_values_creates_missing_secrets_and_reads_current_values():
    client = FakeSecretManagerClient()
    store = SecretManagerConfigStore(config(), client)

    store.write_values("orders", {"DATABASE_URL": "postgres://db", "TOKEN": "secret"})

    assert client.created[0]["secret_id"] == "cloudlift-staging-orders-DATABASE_URL"
    assert store.read_values("orders", ["DATABASE_URL", "TOKEN"]) == {
        "DATABASE_URL": "postgres://db",
        "TOKEN": "secret",
    }


def test_kubernetes_env_refs_point_at_predictable_secret_names():
    store = SecretManagerConfigStore(config(), FakeSecretManagerClient())

    assert store.kubernetes_env_refs("orders", ["DATABASE_URL"]) == [
        {
            "name": "DATABASE_URL",
            "valueFrom": {
                "secretKeyRef": {
                    "name": "cloudlift-staging-orders-DATABASE_URL",
                    "key": "latest",
                }
            },
        }
    ]
