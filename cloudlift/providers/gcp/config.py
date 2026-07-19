import json
import os

from cloudlift.exceptions import UnrecoverableException


CONFIG_PATH_ENV_VAR = "CLOUDLIFT_GCP_CONFIG_PATH"
REQUIRED_FIELDS = (
    "project_id",
    "location",
    "cluster_name",
    "namespace",
    "artifact_registry_repository",
)


class GcpEnvironmentConfig(object):
    def __init__(self, environment, project_id, location, cluster_name, namespace,
                 artifact_registry_repository, service_account=None, path=None):
        self.environment = environment
        self.project_id = project_id
        self.location = location
        self.cluster_name = cluster_name
        self.namespace = namespace
        self.artifact_registry_repository = artifact_registry_repository
        self.service_account = service_account
        self.path = path

    @classmethod
    def default_path(cls, environment):
        return os.path.join(os.getcwd(), ".cloudlift", "gcp-{}.json".format(environment))

    @classmethod
    def path_for(cls, environment, path=None):
        return path or os.environ.get(CONFIG_PATH_ENV_VAR) or cls.default_path(environment)

    @classmethod
    def from_dict(cls, environment, data, path=None):
        values = dict(data or {})
        values.setdefault("namespace", environment)
        missing = [field for field in REQUIRED_FIELDS if not values.get(field)]
        if missing:
            raise UnrecoverableException(
                "Missing required GCP environment configuration fields: {}".format(
                    ", ".join(missing)
                )
            )
        return cls(
            environment=environment,
            project_id=values["project_id"],
            location=values["location"],
            cluster_name=values["cluster_name"],
            namespace=values["namespace"],
            artifact_registry_repository=values["artifact_registry_repository"],
            service_account=values.get("service_account"),
            path=path,
        )

    @classmethod
    def load(cls, environment, path=None):
        config_path = cls.path_for(environment, path)
        if not os.path.exists(config_path):
            raise UnrecoverableException(
                "GCP environment config not found at {}. Create it with "
                "`cloudlift create_environment --provider gcp -e {}` or set {}.".format(
                    config_path,
                    environment,
                    CONFIG_PATH_ENV_VAR,
                )
            )
        with open(config_path) as fp:
            data = json.load(fp)
        return cls.from_dict(environment, data, config_path)

    @classmethod
    def load_or_create(cls, environment, path=None, **overrides):
        config_path = cls.path_for(environment, path)
        data = {}
        if os.path.exists(config_path):
            with open(config_path) as fp:
                data = json.load(fp)
        data.update({key: value for key, value in overrides.items() if value is not None})
        config = cls.from_dict(environment, data, config_path)
        config.save(config_path)
        return config

    def to_dict(self):
        data = {
            "project_id": self.project_id,
            "location": self.location,
            "cluster_name": self.cluster_name,
            "namespace": self.namespace,
            "artifact_registry_repository": self.artifact_registry_repository,
        }
        if self.service_account:
            data["service_account"] = self.service_account
        return data

    def save(self, path=None):
        config_path = path or self.path or self.path_for(self.environment)
        directory = os.path.dirname(config_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(config_path, "w") as fp:
            json.dump(self.to_dict(), fp, indent=2, sort_keys=True)
            fp.write("\n")
        self.path = config_path
        return config_path
