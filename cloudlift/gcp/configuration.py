import json
import os

import click
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from cloudlift.config.logging import log_bold, log_warning
from cloudlift.exceptions import UnrecoverableException


DEFAULT_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".cloudlift", "gcp", "environments")


class GcpEnvironmentConfiguration(object):
    """Local GCP environment configuration for Cloud Run deployments.

    This intentionally uses a separate JSON shape from the AWS DynamoDB-backed
    environment configuration. Only Cloud Run, Artifact Registry, and Secret
    Manager settings are represented here.
    """

    def __init__(self, environment, config_dir=None):
        self.environment = environment
        self.config_dir = config_dir or os.environ.get("CLOUDLIFT_GCP_CONFIG_DIR", DEFAULT_CONFIG_DIR)

    @property
    def config_path(self):
        return os.path.join(self.config_dir, "%s.json" % self.environment)

    def default_config(self):
        return {
            "project_id": "",
            "region": "us-central1",
            "artifact_registry": {
                "location": "us-central1",
                "repository": "cloudlift"
            },
            "cloud_run": {
                "cpu": "1",
                "memory": "512Mi",
                "concurrency": 80,
                "ingress": "INGRESS_TRAFFIC_ALL",
                "service_account": None,
                "vpc_connector": None,
                "allow_unauthenticated": False
            }
        }

    def get_config(self):
        if not os.path.exists(self.config_path):
            raise UnrecoverableException(
                "GCP environment configuration not found for '%s'. Run gcp_create_environment first." % self.environment
            )
        with open(self.config_path) as config_file:
            config = json.load(config_file)
        self._validate_config(config)
        return config

    def update_config(self):
        if os.path.exists(self.config_path):
            current_configuration = self.get_config()
        else:
            log_warning("GCP configuration for this environment was not found. Creating a new local config.")
            current_configuration = self._prompt_for_config()

        edited_config_content = click.edit(json.dumps(current_configuration, indent=4, sort_keys=True))
        if edited_config_content is None:
            log_warning("No changes made.")
            self._set_config(current_configuration)
            return current_configuration

        try:
            updated_configuration = json.loads(edited_config_content)
        except ValueError as error:
            raise UnrecoverableException("Invalid GCP environment JSON: %s" % error)
        self._set_config(updated_configuration)
        return updated_configuration

    def _prompt_for_config(self):
        config = self.default_config()
        config["project_id"] = click.prompt("GCP project ID")
        config["region"] = click.prompt("Cloud Run region", default=config["region"])
        config["artifact_registry"]["location"] = click.prompt(
            "Artifact Registry location", default=config["artifact_registry"]["location"]
        )
        config["artifact_registry"]["repository"] = click.prompt(
            "Artifact Registry Docker repository", default=config["artifact_registry"]["repository"]
        )
        config["cloud_run"]["service_account"] = click.prompt(
            "Cloud Run service account (optional)", default="", show_default=False
        ) or None
        config["cloud_run"]["vpc_connector"] = click.prompt(
            "Cloud Run VPC connector (optional)", default="", show_default=False
        ) or None
        config["cloud_run"]["ingress"] = click.prompt(
            "Cloud Run ingress", default=config["cloud_run"]["ingress"]
        )
        return config

    def _set_config(self, config):
        self._validate_config(config)
        if not os.path.isdir(self.config_dir):
            os.makedirs(self.config_dir)
        with open(self.config_path, "w") as config_file:
            json.dump(config, config_file, indent=4, sort_keys=True)
            config_file.write("\n")
        log_bold("Stored GCP environment configuration at %s" % self.config_path)

    def _validate_config(self, config):
        schema = {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "minLength": 1},
                "region": {"type": "string", "minLength": 1},
                "artifact_registry": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "minLength": 1},
                        "repository": {"type": "string", "minLength": 1}
                    },
                    "required": ["location", "repository"]
                },
                "cloud_run": {
                    "type": "object",
                    "properties": {
                        "cpu": {"type": "string", "minLength": 1},
                        "memory": {"type": "string", "minLength": 1},
                        "concurrency": {"type": "integer", "minimum": 1},
                        "ingress": {"type": "string", "minLength": 1},
                        "service_account": {"type": ["string", "null"]},
                        "vpc_connector": {"type": ["string", "null"]},
                        "allow_unauthenticated": {"type": "boolean"}
                    },
                    "required": ["cpu", "memory", "concurrency", "ingress"]
                }
            },
            "required": ["project_id", "region", "artifact_registry", "cloud_run"]
        }
        try:
            validate(config, schema)
        except ValidationError as validation_error:
            error_path = ".".join([str(path) for path in validation_error.relative_path])
            if error_path:
                raise UnrecoverableException(validation_error.message + " in " + error_path)
            raise UnrecoverableException(validation_error.message)
        return True
