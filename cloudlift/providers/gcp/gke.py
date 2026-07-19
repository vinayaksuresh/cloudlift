class GkeDeployer(object):
    def __init__(self, config, apps_v1_api, core_v1_api):
        self.config = config
        self.apps_v1_api = apps_v1_api
        self.core_v1_api = core_v1_api

    def labels(self, service_name):
        return {"app": service_name, "cloudlift.io/environment": self.config.environment}

    def render_deployment(self, service_name, image, container_port=80, replicas=1,
                          env=None, labels=None):
        labels = labels or self.labels(service_name)
        pod_spec = {
            "containers": [
                {
                    "name": service_name,
                    "image": image,
                    "ports": [{"containerPort": int(container_port)}],
                    "env": env or [],
                }
            ]
        }
        if self.config.service_account:
            pod_spec["serviceAccountName"] = self.config.service_account
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": service_name,
                "namespace": self.config.namespace,
                "labels": labels,
            },
            "spec": {
                "replicas": int(replicas),
                "selector": {"matchLabels": labels},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": pod_spec,
                },
            },
        }

    def render_service(self, service_name, container_port=80, labels=None):
        labels = labels or self.labels(service_name)
        return {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": service_name,
                "namespace": self.config.namespace,
                "labels": labels,
            },
            "spec": {
                "type": "ClusterIP",
                "selector": labels,
                "ports": [{"port": int(container_port), "targetPort": int(container_port)}],
            },
        }

    def apply_service(self, service_name, image, container_port=80, replicas=1,
                      env=None, labels=None):
        deployment = self.render_deployment(
            service_name, image, container_port, replicas, env, labels
        )
        service = self.render_service(service_name, container_port, labels)
        namespace = self.config.namespace
        try:
            self.apps_v1_api.read_namespaced_deployment(service_name, namespace)
            self.apps_v1_api.patch_namespaced_deployment(service_name, namespace, deployment)
        except Exception as exc:
            if getattr(exc, "status", None) not in (404, None):
                raise
            self.apps_v1_api.create_namespaced_deployment(namespace, deployment)
        try:
            self.core_v1_api.read_namespaced_service(service_name, namespace)
            self.core_v1_api.patch_namespaced_service(service_name, namespace, service)
        except Exception as exc:
            if getattr(exc, "status", None) not in (404, None):
                raise
            self.core_v1_api.create_namespaced_service(namespace, service)
        return deployment, service

    def deploy_image(self, service_name, image):
        body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": service_name, "image": image}]
                    }
                }
            }
        }
        return self.apps_v1_api.patch_namespaced_deployment(
            service_name,
            self.config.namespace,
            body,
        )
