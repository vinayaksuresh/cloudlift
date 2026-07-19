import re

import dictdiffer
import click

from cloudlift.config import print_parameter_changes
from cloudlift.config.logging import log_intent, log_warning
from cloudlift.deployment.deployer import read_config
from cloudlift.exceptions import UnrecoverableException

SECRET_KEY_PATTERN = r'^[A-Za-z_][A-Za-z0-9_]*$'


class GcpSecretManagerStore(object):
    def __init__(self, service_name, environment, project_id, client=None):
        self.service_name = service_name
        self.environment = environment
        self.project_id = project_id
        self.client = client or self._default_client()
        self.parent = 'projects/%s' % self.project_id
        self.secret_prefix = 'cloudlift-%s-%s-' % (
            self._safe_secret_part(environment),
            self._safe_secret_part(service_name),
        )

    def get_existing_config_as_string(self):
        environment_configs, _ = self.get_existing_config()
        return '\n'.join('{}={}'.format(key, val) for key, val in sorted(
            environment_configs.items()
        ))

    def get_existing_config(self):
        environment_configs = {}
        environment_config_paths = {}
        for secret in self.client.list_secrets(request={'parent': self.parent}):
            secret_name = secret.name
            secret_id = secret_name.split('/')[-1]
            if not secret_id.startswith(self.secret_prefix):
                continue
            key = secret_id.split(self.secret_prefix, 1)[1]
            version_name = '%s/versions/latest' % secret_name
            environment_config_paths[key] = version_name
            try:
                version = self.client.access_secret_version(request={'name': version_name})
                environment_configs[key] = version.payload.data.decode('UTF-8')
            except Exception:
                environment_configs[key] = ''
        return environment_configs, environment_config_paths

    def edit_config(self):
        env_config_strings = self.get_existing_config_as_string()
        edited_config_content = click.edit(str(env_config_strings))
        if edited_config_content is None:
            log_warning('No changes made, exiting.')
            return
        differences = list(dictdiffer.diff(
            read_config(env_config_strings),
            read_config(edited_config_content)
        ))
        if not differences:
            log_warning('No changes made, exiting.')
            return
        print_parameter_changes(differences)
        if click.confirm('Do you want update the config?'):
            self.set_config(differences)
        else:
            log_warning('Changes aborted.')

    def set_config(self, differences):
        self._validate_changes(differences)
        for secret_change in differences:
            if secret_change[0] == 'change':
                self._add_secret_version(secret_change[1], secret_change[2][1])
            elif secret_change[0] == 'add':
                for added_secret in secret_change[2]:
                    self._create_secret_if_missing(added_secret[0])
                    self._add_secret_version(added_secret[0], added_secret[1])
            elif secret_change[0] == 'remove':
                for deleted_secret in secret_change[2]:
                    self._delete_secret(deleted_secret[0])

    def cloud_run_secret_references(self, service_config):
        _, environment_config_paths = self.get_existing_config()
        return [
            {
                'name': key,
                'value_source': {
                    'secret_key_ref': {
                        'secret': environment_config_paths[key],
                        'version': 'latest',
                    }
                }
            }
            for key in service_config
        ]

    def secret_id_for_key(self, key):
        if not self._is_a_valid_parameter_key(key):
            raise UnrecoverableException("'%s' is not a valid Secret Manager key." % key)
        return self.secret_prefix + key

    def _create_secret_if_missing(self, key):
        secret_id = self.secret_id_for_key(key)
        try:
            self.client.create_secret(
                request={
                    'parent': self.parent,
                    'secret_id': secret_id,
                    'secret': {
                        'replication': {'automatic': {}},
                        'labels': {
                            'cloudlift_environment': self._label_value(self.environment),
                            'cloudlift_service': self._label_value(self.service_name),
                        },
                    },
                }
            )
            log_intent('Created Secret Manager secret for ' + key)
        except Exception as error:
            if type(error).__name__ != 'AlreadyExists':
                raise

    def _add_secret_version(self, key, value):
        self._create_secret_if_missing(key)
        self.client.add_secret_version(
            request={
                'parent': '%s/secrets/%s' % (self.parent, self.secret_id_for_key(key)),
                'payload': {'data': value.encode('UTF-8')},
            }
        )

    def _delete_secret(self, key):
        self.client.delete_secret(
            request={'name': '%s/secrets/%s' % (self.parent, self.secret_id_for_key(key))}
        )

    def _validate_changes(self, differences):
        errors = []
        for secret_change in differences:
            if secret_change[0] == 'change':
                if not self._is_a_valid_parameter_key(secret_change[1]):
                    errors.append("'%s' is not a valid key." % secret_change[1])
            elif secret_change[0] == 'add':
                for added_secret in secret_change[2]:
                    if not self._is_a_valid_parameter_key(added_secret[0]):
                        errors.append("'%s' is not a valid key." % added_secret[0])
        if errors:
            raise UnrecoverableException('Environment variables validation failed with errors: ' + ', '.join(errors))
        return True

    def _is_a_valid_parameter_key(self, key):
        return bool(re.match(SECRET_KEY_PATTERN, key))

    def _safe_secret_part(self, value):
        return re.sub(r'[^A-Za-z0-9_-]', '-', value).strip('-')

    def _label_value(self, value):
        return re.sub(r'[^a-z0-9_-]', '_', value.lower())[:63]

    def _default_client(self):
        try:
            from google.cloud import secretmanager
        except ImportError:
            raise UnrecoverableException('google-cloud-secret-manager is required for GCP secrets support.')
        return secretmanager.SecretManagerServiceClient()
