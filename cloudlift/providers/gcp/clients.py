import base64
import os

from cloudlift.exceptions import UnrecoverableException


class GcpClients(object):
    def __init__(self, config, container_client, secret_manager_client,
                 artifact_registry_client, core_v1_api, apps_v1_api):
        self.config = config
        self.container_client = container_client
        self.secret_manager_client = secret_manager_client
        self.artifact_registry_client = artifact_registry_client
        self.core_v1_api = core_v1_api
        self.apps_v1_api = apps_v1_api

    @classmethod
    def from_adc(cls, config):
        try:
            import google.auth
            from google.auth.transport.requests import Request
            from google.cloud import artifactregistry_v1
            from google.cloud import container_v1
            from google.cloud import secretmanager
            from kubernetes import client as kubernetes_client
        except ImportError as exc:
            raise UnrecoverableException(
                "GCP provider dependencies are not installed: {}".format(exc)
            )

        credentials, _project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        if not credentials.valid:
            credentials.refresh(Request())

        container_client = container_v1.ClusterManagerClient(credentials=credentials)
        cluster = container_client.get_cluster(
            name="projects/{}/locations/{}/clusters/{}".format(
                config.project_id,
                config.location,
                config.cluster_name,
            )
        )
        kube_config = kubernetes_client.Configuration()
        kube_config.host = "https://{}".format(cluster.endpoint)
        kube_config.verify_ssl = True
        kube_config.api_key = {"authorization": "Bearer {}".format(credentials.token)}
        ca_data = getattr(getattr(cluster, "master_auth", None), "cluster_ca_certificate", None)
        if ca_data:
            ca_path = os.path.join(os.getcwd(), ".cloudlift", "gke-ca-{}.crt".format(config.environment))
            directory = os.path.dirname(ca_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory)
            with open(ca_path, "wb") as fp:
                fp.write(base64.b64decode(ca_data))
            kube_config.ssl_ca_cert = ca_path
        api_client = kubernetes_client.ApiClient(kube_config)
        return cls(
            config=config,
            container_client=container_client,
            secret_manager_client=secretmanager.SecretManagerServiceClient(credentials=credentials),
            artifact_registry_client=artifactregistry_v1.ArtifactRegistryClient(credentials=credentials),
            core_v1_api=kubernetes_client.CoreV1Api(api_client),
            apps_v1_api=kubernetes_client.AppsV1Api(api_client),
        )

    def ensure_namespace_exists(self):
        namespace = self.config.namespace
        try:
            self.core_v1_api.read_namespace(namespace)
            return False
        except Exception as exc:
            if getattr(exc, "status", None) not in (404, None):
                raise
        body = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}
        self.core_v1_api.create_namespace(body)
        return True
