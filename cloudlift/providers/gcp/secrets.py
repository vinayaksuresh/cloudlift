import re


class SecretManagerConfigStore(object):
    def __init__(self, config, client):
        self.config = config
        self.client = client

    def secret_id(self, service_name, key):
        raw = "cloudlift-{}-{}-{}".format(self.config.environment, service_name, key)
        return re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")[:255]

    def secret_path(self, service_name, key):
        secret_id = self.secret_id(service_name, key)
        if hasattr(self.client, "secret_path"):
            return self.client.secret_path(self.config.project_id, secret_id)
        return "projects/{}/secrets/{}".format(self.config.project_id, secret_id)

    def secret_version_path(self, service_name, key, version="latest"):
        return "{}/versions/{}".format(self.secret_path(service_name, key), version)

    def read_value(self, service_name, key):
        response = self.client.access_secret_version(
            request={"name": self.secret_version_path(service_name, key)}
        )
        payload = response.payload.data
        if isinstance(payload, bytes):
            return payload.decode("utf-8")
        return payload

    def read_values(self, service_name, keys):
        return {key: self.read_value(service_name, key) for key in keys}

    def write_value(self, service_name, key, value):
        parent = "projects/{}".format(self.config.project_id)
        secret_path = self.secret_path(service_name, key)
        try:
            self.client.get_secret(request={"name": secret_path})
        except Exception:
            self.client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": self.secret_id(service_name, key),
                    "secret": {"replication": {"automatic": {}}},
                }
            )
        data = value.encode("utf-8") if isinstance(value, str) else value
        return self.client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": data}}
        )

    def write_values(self, service_name, values):
        return {key: self.write_value(service_name, key, value) for key, value in values.items()}

    def kubernetes_env_refs(self, service_name, keys):
        return [
            {
                "name": key,
                "valueFrom": {
                    "secretKeyRef": {
                        "name": self.secret_id(service_name, key),
                        "key": "latest",
                    }
                },
            }
            for key in keys
        ]
