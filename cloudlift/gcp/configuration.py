import copy
import json
import os

import click
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from cloudlift.config.logging import log_bold, log_err, log_warning
from cloudlift.config.utils import ConfigUtils
from cloudlift.exceptions import UnrecoverableException

CONFIG_ENV_VAR = 'CLOUDLIFT_GCP_CONFIG_FILE'
DEFAULT_SERVICE_DEFAULTS = {
    'cpu': '1000m',
    'memory': '512Mi',
    'concurrency': 80,
    'ingress': 'INGRESS_TRAFFIC_ALL',
    'service_account': None,
    'vpc_connector': None,
}
ALLOWED_INGRESS = [
    'INGRESS_TRAFFIC_ALL',
    'INGRESS_TRAFFIC_INTERNAL_ONLY',
    'INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER',
]


def default_config_path():
    return os.path.expanduser(os.environ.get(
        CONFIG_ENV_VAR,
        os.path.join('~', '.cloudlift', 'gcp_environments.json')
    ))


class GcpEnvironmentConfiguration(object):
    '''Handles local Cloudlift configuration for GCP Cloud Run environments.'''

    def __init__(self, environment=None, config_path=None):
        self.environment = environment
        self.config_path = os.path.expanduser(config_path or default_config_path())
        self.config_utils = ConfigUtils(changes_validation_function=self._validate_changes)

    def get_config(self):
        configuration = self._read_all()
        try:
            return configuration['environments'][self.environment]
        except KeyError:
            raise UnrecoverableException(
                'GCP environment configuration not found. Does this environment exist?'
            )

    def get_all_environments(self):
        return sorted(self._read_all().get('environments', {}).keys())

    def create_or_update_config(self, project_id, region,
                                artifact_registry_location,
                                artifact_registry_repository,
                                service_account=None, vpc_connector=None,
                                ingress=None, cpu=None, memory=None,
                                concurrency=None):
        all_config = self._read_all()
        env_config = {
            'project_id': project_id,
            'region': region,
            'artifact_registry': {
                'location': artifact_registry_location,
                'repository': artifact_registry_repository,
            },
            'service_defaults': copy.deepcopy(DEFAULT_SERVICE_DEFAULTS),
        }
        if service_account is not None:
            env_config['service_defaults']['service_account'] = service_account
        if vpc_connector is not None:
            env_config['service_defaults']['vpc_connector'] = vpc_connector
        if ingress is not None:
            env_config['service_defaults']['ingress'] = ingress
        if cpu is not None:
            env_config['service_defaults']['cpu'] = cpu
        if memory is not None:
            env_config['service_defaults']['memory'] = memory
        if concurrency is not None:
            env_config['service_defaults']['concurrency'] = concurrency

        all_config.setdefault('environments', {})[self.environment] = env_config
        self._set_config(all_config)
        log_bold('Saved GCP environment configuration for ' + self.environment)
        return env_config

    def update_config(self):
        current_configuration = self._read_all()
        if self.environment not in current_configuration.get('environments', {}):
            log_warning('GCP configuration for this environment was not found. Initiating prompts.')
            self.create_or_update_config(
                project_id=click.prompt('GCP project ID'),
                region=click.prompt('Cloud Run region', default='us-central1'),
                artifact_registry_location=click.prompt('Artifact Registry location', default='us'),
                artifact_registry_repository=click.prompt('Artifact Registry Docker repository'),
                service_account=click.prompt('Cloud Run service account (optional)', default='', show_default=False) or None,
                vpc_connector=click.prompt('VPC connector resource name (optional)', default='', show_default=False) or None,
                ingress=click.prompt('Cloud Run ingress', default=DEFAULT_SERVICE_DEFAULTS['ingress']),
            )
            current_configuration = self._read_all()

        updated_configuration = self.config_utils.fault_tolerant_edit_config(
            current_configuration=current_configuration
        )
        if updated_configuration is None:
            log_warning('No changes made.')
            return
        if updated_configuration == current_configuration:
            log_warning('No changes made.')
            return
        if click.confirm('Do you want to update the GCP config?'):
            self._set_config(updated_configuration)
        else:
            log_warning('Changes aborted.')

    def _read_all(self):
        if not os.path.exists(self.config_path):
            return {'environments': {}}
        try:
            with open(self.config_path) as config_file:
                data = json.load(config_file)
        except ValueError:
            raise UnrecoverableException('Unable to parse GCP configuration JSON.')
        if not data:
            return {'environments': {}}
        return data

    def _set_config(self, config):
        self._validate_changes(config)
        directory = os.path.dirname(self.config_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(self.config_path, 'w') as config_file:
            json.dump(config, config_file, indent=4, sort_keys=True)
            config_file.write('\n')

    def _validate_changes(self, configuration):
        log_bold('\nValidating GCP schema..')
        schema = {
            'type': 'object',
            'properties': {
                'environments': {
                    'type': 'object',
                    'additionalProperties': {
                        'type': 'object',
                        'properties': {
                            'project_id': {'type': 'string', 'minLength': 1},
                            'region': {'type': 'string', 'minLength': 1},
                            'artifact_registry': {
                                'type': 'object',
                                'properties': {
                                    'location': {'type': 'string', 'minLength': 1},
                                    'repository': {'type': 'string', 'minLength': 1},
                                },
                                'required': ['location', 'repository'],
                            },
                            'service_defaults': {
                                'type': 'object',
                                'properties': {
                                    'cpu': {'type': 'string', 'minLength': 1},
                                    'memory': {'type': 'string', 'minLength': 1},
                                    'concurrency': {'type': 'integer', 'minimum': 1},
                                    'ingress': {'type': 'string', 'enum': ALLOWED_INGRESS},
                                    'service_account': {'type': ['string', 'null']},
                                    'vpc_connector': {'type': ['string', 'null']},
                                },
                            },
                        },
                        'required': ['project_id', 'region', 'artifact_registry'],
                    },
                },
            },
            'required': ['environments'],
        }
        try:
            validate(configuration, schema)
        except ValidationError as validation_error:
            log_err('GCP schema validation failed!')
            error_path = '.'.join([str(path) for path in validation_error.relative_path])
            if error_path:
                raise UnrecoverableException(validation_error.message + ' in ' + error_path)
            raise UnrecoverableException(validation_error.message)
        log_bold('GCP schema valid!')
