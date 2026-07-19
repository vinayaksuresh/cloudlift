import re

from cloudlift.config.logging import log_err
from cloudlift.exceptions import UnrecoverableException


class GcpSecretManagerStore(object):
    """Manage per-service Cloud Run secrets in GCP Secret Manager."""

    ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    SECRET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,255}$")

    def __init__(self, service_name, environment, project_id, client=None):
        self.service_name = service_name
        self.environment = environment
        self.project_id = project_id
        self.client = client or self._build_client()

    def _build_client(self):
        try:
            from google.cloud import secretmanager
        except ImportError:
            raise UnrecoverableException("google-cloud-secret-manager is required for GCP secret operations.")
        return secretmanager.SecretManagerServiceClient()

    @property
    def parent(self):
        return "projects/%s" % self.project_id

    @property
    def secret_prefix(self):
        return "cloudlift-%s-%s-" % (self._slug(self.environment), self._slug(self.service_name))

    def secret_id_for_key(self, key):
        if not self._is_a_valid_parameter_key(key):
            raise UnrecoverableException("'%s' is not a valid GCP environment key." % key)
        secret_id = self.secret_prefix + key
        if not self.SECRET_ID_RE.match(secret_id):
            raise UnrecoverableException("Secret ID for '%s' is not valid for GCP Secret Manager." % key)
        return secret_id

    def get_existing_config_as_string(self):
        environment_configs, _ = self.get_existing_config()
        return '\n'.join('{}={}'.format(key, val) for key, val in sorted(environment_configs.items()))

    def get_existing_config(self):
        environment_configs = {}
        environment_config_paths = {}
        for secret in self.client.list_secrets(request={"parent": self.parent}):
            secret_id = secret.name.split("/")[-1]
            if not secret_id.startswith(self.secret_prefix):
                continue
            key = secret_id[len(self.secret_prefix):]
            environment_config_paths[key] = self.secret_version_reference(key)
            try:
                response = self.client.access_secret_version(request={"name": self.secret_version_reference(key)})
                environment_configs[key] = response.payload.data.decode("UTF-8")
            except Exception:
                environment_configs[key] = ""
        return environment_configs, environment_config_paths

    def set_config(self, differences):
        self._validate_changes(differences)
        for parameter_change in differences:
            if parameter_change[0] == 'change':
                self._put_secret(parameter_change[1], parameter_change[2][1], create=False)
            elif parameter_change[0] == 'add':
                for added_parameter in parameter_change[2]:
                    self._put_secret(added_parameter[0], added_parameter[1], create=True)
            elif parameter_change[0] == 'remove':
                for removed_parameter in parameter_change[2]:
                    self.client.delete_secret(request={"name": self.secret_name_for_key(removed_parameter[0])})

    def secret_references_for_keys(self, keys):
        refs = {}
        for key in keys:
            refs[key] = self.secret_version_reference(key)
        return refs

    def secret_name_for_key(self, key):
        return "%s/secrets/%s" % (self.parent, self.secret_id_for_key(key))

    def secret_version_reference(self, key, version="latest"):
        return "%s/versions/%s" % (self.secret_name_for_key(key), version)

    def _put_secret(self, key, value, create):
        secret_name = self.secret_name_for_key(key)
        if create:
            try:
                self.client.create_secret(
                    request={
                        "parent": self.parent,
                        "secret_id": self.secret_id_for_key(key),
                        "secret": {"replication": {"automatic": {}}}
                    }
                )
            except Exception as error:
                if "AlreadyExists" not in type(error).__name__ and "already exists" not in str(error):
                    raise
        self.client.add_secret_version(
            request={"parent": secret_name, "payload": {"data": value.encode("UTF-8")}}
        )

    def _validate_changes(self, differences):
        errors = []
        for parameter_change in differences:
            if parameter_change[0] == 'change':
                if not self._is_a_valid_parameter_key(parameter_change[1]):
                    errors.append("'%s' is not a valid key." % parameter_change[1])
            elif parameter_change[0] == 'add':
                for added_parameter in parameter_change[2]:
                    if not self._is_a_valid_parameter_key(added_parameter[0]):
                        errors.append("'%s' is not a valid key." % added_parameter[0])
        if errors:
            for error in errors:
                log_err(error)
            raise UnrecoverableException("Environment variables validation failed with above errors.")
        return True

    def _is_a_valid_parameter_key(self, key):
        return bool(self.ENV_KEY_RE.match(key))

    def _slug(self, value):
        return re.sub(r"[^a-z0-9-]", "-", value.lower()).strip("-")
