from cloudlift.providers.gcp.config import GcpEnvironmentConfig
from cloudlift.providers.gcp.gke import GkeDeployer


class NotFound(Exception):
    status = 404


class FakeAppsV1Api(object):
    def __init__(self):
        self.deployments = {}
        self.created = []
        self.patched = []

    def read_namespaced_deployment(self, name, namespace):
        key = (namespace, name)
        if key not in self.deployments:
            raise NotFound()
        return self.deployments[key]

    def create_namespaced_deployment(self, namespace, body):
        self.created.append((namespace, body))
        self.deployments[(namespace, body["metadata"]["name"])] = body
        return body

    def patch_namespaced_deployment(self, name, namespace, body):
        self.patched.append((namespace, name, body))
        self.deployments[(namespace, name)] = body
        return body


class FakeCoreV1Api(object):
    def __init__(self):
        self.services = {}
        self.created = []
        self.patched = []

    def read_namespaced_service(self, name, namespace):
        key = (namespace, name)
        if key not in self.services:
            raise NotFound()
        return self.services[key]

    def create_namespaced_service(self, namespace, body):
        self.created.append((namespace, body))
        self.services[(namespace, body["metadata"]["name"])] = body
        return body

    def patch_namespaced_service(self, name, namespace, body):
        self.patched.append((namespace, name, body))
        self.services[(namespace, name)] = body
        return body


def config():
    return GcpEnvironmentConfig(
        environment="staging",
        project_id="project-1",
        location="asia-south1",
        cluster_name="cluster-1",
        namespace="apps",
        artifact_registry_repository="services",
        service_account="app-runner",
    )


def test_render_deployment_and_service_include_minimal_gke_shape():
    deployer = GkeDeployer(config(), FakeAppsV1Api(), FakeCoreV1Api())

    deployment = deployer.render_deployment(
        "orders",
        "image:tag",
        container_port=8080,
        replicas=3,
        env=[{"name": "TOKEN", "value": "x"}],
    )
    service = deployer.render_service("orders", container_port=8080)

    assert deployment["metadata"]["namespace"] == "apps"
    assert deployment["spec"]["replicas"] == 3
    assert deployment["spec"]["template"]["spec"]["serviceAccountName"] == "app-runner"
    assert deployment["spec"]["template"]["spec"]["containers"][0] == {
        "name": "orders",
        "image": "image:tag",
        "ports": [{"containerPort": 8080}],
        "env": [{"name": "TOKEN", "value": "x"}],
    }
    assert service["spec"]["ports"] == [{"port": 8080, "targetPort": 8080}]
    assert service["spec"]["selector"] == {"app": "orders", "cloudlift.io/environment": "staging"}


def test_apply_service_creates_then_patches_workload():
    apps = FakeAppsV1Api()
    core = FakeCoreV1Api()
    deployer = GkeDeployer(config(), apps, core)

    deployer.apply_service("orders", "image:v1")
    deployer.apply_service("orders", "image:v2")

    assert apps.created[0][0] == "apps"
    assert core.created[0][0] == "apps"
    assert apps.patched[0][1] == "orders"
    assert apps.patched[0][2]["spec"]["template"]["spec"]["containers"][0]["image"] == "image:v2"
    assert core.patched[0][1] == "orders"


def test_deploy_image_patches_deployment_container_image():
    apps = FakeAppsV1Api()
    deployer = GkeDeployer(config(), apps, FakeCoreV1Api())

    deployer.deploy_image("orders", "image:v3")

    assert apps.patched == [
        (
            "apps",
            "orders",
            {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{"name": "orders", "image": "image:v3"}]
                        }
                    }
                }
            },
        )
    ]
