from cloudlift.providers.gcp.artifact_registry import ArtifactRegistryClient
from cloudlift.providers.gcp.config import GcpEnvironmentConfig


def config():
    return GcpEnvironmentConfig(
        environment="staging",
        project_id="project-1",
        location="asia-south1",
        cluster_name="cluster-1",
        namespace="apps",
        artifact_registry_repository="services",
    )


def test_image_uri_is_deterministic_for_service_and_version():
    image = ArtifactRegistryClient(config()).image_uri("orders", "abc123")

    assert image == "asia-south1-docker.pkg.dev/project-1/services/orders:abc123"


def test_tag_and_push_tags_local_image_and_all_requested_tags(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "cloudlift.providers.gcp.artifact_registry.subprocess.check_call",
        lambda args: calls.append(args),
    )

    pushed = ArtifactRegistryClient(config()).tag_and_push(
        "orders",
        "abc123",
        ["stable"],
    )

    assert pushed == [
        "asia-south1-docker.pkg.dev/project-1/services/orders:abc123",
        "asia-south1-docker.pkg.dev/project-1/services/orders:stable",
    ]
    assert calls == [
        ["docker", "tag", "orders:abc123", "asia-south1-docker.pkg.dev/project-1/services/orders:abc123"],
        ["docker", "push", "asia-south1-docker.pkg.dev/project-1/services/orders:abc123"],
        ["docker", "tag", "orders:abc123", "asia-south1-docker.pkg.dev/project-1/services/orders:stable"],
        ["docker", "push", "asia-south1-docker.pkg.dev/project-1/services/orders:stable"],
    ]
