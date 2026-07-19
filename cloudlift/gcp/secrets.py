import re

from cloudlift.config.logging import log_err
from cloudlift.exceptions import UnrecoverableException

ENV_KEY_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


class GcpSecretManagerStore(object):
    def __init__(self, service_name, environment, project_id, client=None):
        self.service_name = service_name
        self.environment = environment
        self.project_id = project_id
        self.client = client or self._build_client()

    def get_existing_config_as_string(self):
        environment_configs, _ = self.get_existing_config()
        return '\n'.join('{}={}'.format(key, val) for key, val in sorted(environment_configs.items()))

    def get_existing_config(self):
        environment_configs = {}
        environment_configs_path = {}
        parent = self.project_path
        for secret in self.client.list_secrets(request={'parent': parent}):
            labels = getattr(secret, 'labels', {}) or {}
            if labels.get('cloudlift_environment') != self.environment or labels.get('cloudlift_service') != self.service_name:
                continue
            key = labels.get('cloudlift_key') or self._key_from_secret_name(secret.name)
            version_name = secret.name + '/versions/latest'
            try:
                version = self.client.access_secret_version(request={'name': version_name})
                value = version.payload.data.decode('UTF-8')
            except Exception:
                value = ''
            environment_configs[key] = value
            environment_configs_path[key] = self.secret_reference(key)
        return environment_configs, environment_configs_path

    def set_config(self, differences):
        self._validate_changes(differences)
        for secret_change in differences:
            if secret_change[0] == 'change':
                self._put_secret(secret_change[1], secret_change[2][1], exists=True)
            elif secret_change[0] == 'add':
                for added_secret in secret_change[2]:
                    self._put_secret(added_secret[0], added_secret[1], exists=False)
            elif secret_change[0] == 'remove':
                for removed_secret in secret_change[2]:
                    self.client.delete_secret(request={'name': self.secret_name(removed_secret[0])})

    def secret_references_for_keys(self, keys):
        missing = [key for key in keys if not self._is_a_valid_parameter_key(key)]
        if missing:
            raise UnrecoverableException('Invalid GCP secret keys: ' + ', '.join(missing))
        return {key: self.secret_reference(key) for key in keys}

    def secret_name(self, key):
        return '{}/secrets/{}'.format(self.project_path, self.secret_id(key))

    def secret_reference(self, key):
        return '{}:latest'.format(self.secret_name(key))

    @property
    def project_path(self):
        return 'projects/{}'.format(self.project_id)

    def secret_id(self, key):
        safe_service = re.sub(r'[^A-Za-z0-9_-]', '-', self.service_name)
        safe_environment = re.sub(r'[^A-Za-z0-9_-]', '-', self.environment)
        return 'cloudlift-{}-{}-{}'.format(safe_environment, safe_service, key)

    def _put_secret(self, key, value, exists):
        if not exists:
            self.client.create_secret(
                request={
                    'parent': self.project_path,
                    'secret_id': self.secret_id(key),
                    'secret': {
                        'replication': {'automatic': {}},
                        'labels': {
                            'cloudlift_environment': self.environment,
                            'cloudlift_service': self.service_name,
                            'cloudlift_key': key
                        }
                    }
                }
            )
        self.client.add_secret_version(
            request={
                'parent': self.secret_name(key),
                'payload': {'data': value.encode('UTF-8')}
            }
        )

    def _validate_changes(self, differences):
        errors = []
        for secret_change in differences:
            if secret_change[0] == 'change':
                self._validate_key_value(secret_change[1], secret_change[2][1], errors)
            elif secret_change[0] == 'add':
                for added_secret in secret_change[2]:
                    self._validate_key_value(added_secret[0], added_secret[1], errors)
        if errors:
            for error in errors:
                log_err(error)
            raise UnrecoverableException('GCP Secret Manager validation failed with above errors.')
        return True

    def _validate_key_value(self, key, value, errors):
        if not self._is_a_valid_parameter_key(key):
            errors.append("'%s' is not a valid key." % key)
        if value == '':
            errors.append("'' is not a valid value for key '%s'" % key)

    def _is_a_valid_parameter_key(self, key):
        return bool(ENV_KEY_PATTERN.match(key))

    def _key_from_secret_name(self, name):
        prefix = self.secret_id('')
        secret_id = name.split('/secrets/')[-1]
        if secret_id.startswith(prefix):
            return secret_id[len(prefix):]
        return secret_id

    def _build_client(self):
        from google.cloud import secretmanager
        return secretmanager.SecretManagerServiceClient()
