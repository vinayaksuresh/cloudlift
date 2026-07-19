import re

import dictdiffer

from cloudlift.config.logging import log_err, log_intent
from cloudlift.deployment.deployer import read_config
from cloudlift.exceptions import UnrecoverableException

VALID_ENV_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def to_gcp_name(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


class GcpSecretManagerStore(object):
    def __init__(self, service_name, environment, project_id, client=None):
        self.service_name = service_name
        self.environment = environment
        self.project_id = project_id
        self.parent = 'projects/%s' % self.project_id
        self.client = client or self._build_client()

    def get_existing_config_as_string(self):
        environment_configs, _ = self.get_existing_config()
        return '\n'.join('{}={}'.format(key, val) for key, val in sorted(
            environment_configs.items()
        ))

    def get_existing_config(self):
        environment_configs = {}
        environment_config_paths = {}
        for secret in self.client.list_secrets(request={'parent': self.parent}):
            secret_name = self._get_name(secret)
            secret_id = secret_name.split('/secrets/')[-1]
            key = self._key_from_secret_id(secret_id)
            if key is None:
                continue
            version_name = secret_name + '/versions/latest'
            payload = self.client.access_secret_version(
                request={'name': version_name}
            ).payload.data.decode('UTF-8')
            environment_configs[key] = payload
            environment_config_paths[key] = {
                'secret': secret_name,
                'version': 'latest',
            }
        return environment_configs, environment_config_paths

    def set_config_from_string(self, updated_config_content):
        existing_config = self.get_existing_config_as_string()
        differences = list(dictdiffer.diff(
            read_config(existing_config),
            read_config(updated_config_content)
        ))
        self.set_config(differences)

    def set_config(self, differences):
        self._validate_changes(differences)
        for parameter_change in differences:
            if parameter_change[0] == 'change':
                self._put_secret(parameter_change[1], parameter_change[2][1])
            elif parameter_change[0] == 'add':
                for added_parameter in parameter_change[2]:
                    self._put_secret(added_parameter[0], added_parameter[1])
            elif parameter_change[0] == 'remove':
                for removed_parameter in parameter_change[2]:
                    self._delete_secret(removed_parameter[0])

    def _put_secret(self, key, value):
        secret_name = self._secret_name(key)
        try:
            self.client.get_secret(request={'name': secret_name})
        except Exception:
            secret = self.client.create_secret(request={
                'parent': self.parent,
                'secret_id': self._secret_id(key),
                'secret': {'replication': {'automatic': {}}},
            })
            secret_name = self._get_name(secret)
            log_intent('Created GCP secret ' + secret_name)
        self.client.add_secret_version(request={
            'parent': secret_name,
            'payload': {'data': value.encode('UTF-8')},
        })

    def _delete_secret(self, key):
        try:
            self.client.delete_secret(request={'name': self._secret_name(key)})
        except Exception:
            pass

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
            elif parameter_change[0] == 'remove':
                pass
        if errors:
            for error in errors:
                log_err(error)
            raise UnrecoverableException('Environment variables validation failed with above errors.')
        return True

    def _is_a_valid_parameter_key(self, key):
        return bool(VALID_ENV_KEY.match(key))

    def _secret_prefix(self):
        return 'cloudlift-%s-%s-' % (
            to_gcp_name(self.environment),
            to_gcp_name(self.service_name),
        )

    def _secret_id(self, key):
        return self._secret_prefix() + to_gcp_name(key)

    def _secret_name(self, key):
        return '%s/secrets/%s' % (self.parent, self._secret_id(key))

    def _key_from_secret_id(self, secret_id):
        prefix = self._secret_prefix()
        if not secret_id.startswith(prefix):
            return None
        return secret_id[len(prefix):].replace('-', '_').upper()

    def _get_name(self, resource):
        if isinstance(resource, dict):
            return resource['name']
        return resource.name

    def _build_client(self):
        from google.cloud import secretmanager
        return secretmanager.SecretManagerServiceClient()
