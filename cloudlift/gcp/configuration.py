import copy
import json
import os

import dictdiffer
from click import confirm
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from cloudlift.config import print_json_changes
from cloudlift.config.logging import log_bold, log_err, log_warning
from cloudlift.config.utils import ConfigUtils
from cloudlift.exceptions import UnrecoverableException
from cloudlift.version import VERSION

DEFAULT_CONFIG_PATH = os.path.expanduser('~/.cloudlift/gcp_environments.json')


class GcpEnvironmentConfiguration(object):
    '''Handles local GCP Cloud Run environment configuration.'''

    DEFAULT_SERVICE_DEFAULTS = {
        'cpu': '1',
        'memory': '512Mi',
        'concurrency': 80,
        'min_instances': 0,
        'max_instances': 100,
        'timeout': '300s',
    }

    def __init__(self, environment, config_path=None):
        self.environment = environment
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config_utils = ConfigUtils(changes_validation_function=self._validate_changes)

    def get_config(self):
        all_config = self._read_all_config()
        try:
            environment_config = all_config[self.environment]
        except KeyError:
            raise UnrecoverableException(
                'GCP environment configuration not found. Run `cloudlift gcp_create_environment -e %s` first.' % self.environment
            )
        self._validate_environment_config(environment_config)
        return environment_config

    def create_config(self, project_id, region, artifact_registry_location,
                      artifact_registry_repository, service_account=None,
                      vpc_connector=None, ingress='INGRESS_TRAFFIC_ALL',
                      service_defaults=None):
        environment_config = {
            'project_id': project_id,
            'region': region,
            'artifact_registry': {
                'location': artifact_registry_location,
                'repository': artifact_registry_repository,
            },
            'cloud_run': {
                'service_defaults': self._service_defaults(service_defaults),
                'ingress': ingress,
            },
            'cloudlift_version': VERSION,
        }
        if service_account:
            environment_config['cloud_run']['service_account'] = service_account
        if vpc_connector:
            environment_config['cloud_run']['vpc_connector'] = vpc_connector

        self._validate_environment_config(environment_config)
        all_config = self._read_all_config(allow_missing=True)
        all_config[self.environment] = environment_config
        self._write_all_config(all_config)
        log_bold('Saved GCP environment configuration for ' + self.environment)
        return environment_config

    def update_config(self):
        all_config = self._read_all_config()
        if self.environment not in all_config:
            raise UnrecoverableException(
                'GCP environment configuration not found. Run `cloudlift gcp_create_environment -e %s` first.' % self.environment
            )
        current_configuration = copy.deepcopy(all_config[self.environment])
        updated_configuration = self.config_utils.fault_tolerant_edit_config(
            current_configuration=current_configuration,
            inject_version=False
        )
        if updated_configuration is None:
            log_warning('No changes made.')
            return
        differences = list(dictdiffer.diff(current_configuration, updated_configuration))
        if not differences:
            log_warning('No changes made.')
            return
        print_json_changes(differences)
        if confirm('Do you want to update the GCP environment config?'):
            self._validate_environment_config(updated_configuration)
            all_config[self.environment] = updated_configuration
            self._write_all_config(all_config)
        else:
            log_warning('Changes aborted.')

    def _service_defaults(self, service_defaults=None):
        defaults = copy.deepcopy(self.DEFAULT_SERVICE_DEFAULTS)
        if service_defaults:
            defaults.update(service_defaults)
        return defaults

    def _read_all_config(self, allow_missing=False):
        if not os.path.exists(self.config_path):
            if allow_missing:
                return {}
            raise UnrecoverableException(
                'GCP configuration file not found at %s. Run `cloudlift gcp_create_environment` first.' % self.config_path
            )
        with open(self.config_path) as config_file:
            try:
                config = json.load(config_file)
            except ValueError as error:
                raise UnrecoverableException('Unable to parse GCP configuration file: %s' % error)
        if not isinstance(config, dict):
            raise UnrecoverableException('GCP configuration file must contain a JSON object.')
        return config

    def _write_all_config(self, config):
        directory = os.path.dirname(self.config_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)
        with open(self.config_path, 'w') as config_file:
            json.dump(config, config_file, indent=4, sort_keys=True)
            config_file.write('\n')

    def _validate_changes(self, configuration):
        self._validate_environment_config(configuration)
        return True

    def _validate_environment_config(self, configuration):
        log_bold('\nValidating GCP configuration schema..')
        schema = {
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
                'cloud_run': {
                    'type': 'object',
                    'properties': {
                        'service_account': {'type': 'string'},
                        'vpc_connector': {'type': 'string'},
                        'ingress': {
                            'type': 'string',
                            'pattern': '^(INGRESS_TRAFFIC_ALL|INGRESS_TRAFFIC_INTERNAL_ONLY|INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER)$'
                        },
                        'service_defaults': {
                            'type': 'object',
                            'properties': {
                                'cpu': {'type': 'string'},
                                'memory': {'type': 'string'},
                                'concurrency': {'type': 'integer', 'minimum': 1},
                                'min_instances': {'type': 'integer', 'minimum': 0},
                                'max_instances': {'type': 'integer', 'minimum': 0},
                                'timeout': {'type': 'string'},
                            },
                            'required': ['cpu', 'memory', 'concurrency'],
                        },
                    },
                    'required': ['service_defaults'],
                },
                'cloudlift_version': {'type': 'string'},
            },
            'required': ['project_id', 'region', 'artifact_registry', 'cloud_run'],
        }
        try:
            validate(configuration, schema)
        except ValidationError as validation_error:
            log_err('GCP schema validation failed!')
            error_path = str('.'.join(list(validation_error.relative_path)))
            if error_path:
                raise UnrecoverableException(validation_error.message + ' in ' + error_path)
            raise UnrecoverableException(validation_error.message)
        log_bold('GCP schema valid!')
