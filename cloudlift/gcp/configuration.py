import json
import os

import click
import dictdiffer

from cloudlift.config import print_json_changes
from cloudlift.config.logging import log_warning
from cloudlift.config.utils import ConfigUtils
from cloudlift.exceptions import UnrecoverableException

DEFAULT_CONFIG_FILE = os.path.expanduser('~/.cloudlift/gcp_environments.json')
VALID_INGRESS_VALUES = ['INGRESS_TRAFFIC_ALL', 'INGRESS_TRAFFIC_INTERNAL_ONLY', 'INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER']


class GcpEnvironmentConfiguration(object):
    def __init__(self, environment=None, config_file=None):
        self.environment = environment
        self.config_file = config_file or os.environ.get('CLOUDLIFT_GCP_CONFIG_FILE', DEFAULT_CONFIG_FILE)
        self.config_utils = ConfigUtils(changes_validation_function=self._validate_changes)

    def get_config(self):
        configurations = self._read_config_file()
        try:
            return configurations[self.environment]
        except KeyError:
            raise UnrecoverableException('GCP environment configuration not found. Does this environment exist?')

    def update_config(self):
        configurations = self._read_config_file()
        if self.environment not in configurations:
            configurations[self.environment] = self._prompt_for_config()
            self._write_config_file(configurations)
        self._edit_config()

    def set_config(self, config):
        configurations = self._read_config_file()
        configurations[self.environment] = config
        self._write_config_file(configurations)

    def _edit_config(self):
        configurations = self._read_config_file()
        current_configuration = configurations.get(self.environment, self._default_config())
        updated_configuration = self.config_utils.fault_tolerant_edit_config(
            current_configuration=current_configuration
        )
        if updated_configuration is None:
            log_warning('No changes made.')
            return
        differences = list(dictdiffer.diff(current_configuration, updated_configuration))
        if not differences:
            log_warning('No changes made.')
            return
        print_json_changes(differences)
        if click.confirm('Do you want to update the GCP config?'):
            configurations[self.environment] = updated_configuration
            self._write_config_file(configurations)
        else:
            log_warning('Changes aborted.')

    def _prompt_for_config(self):
        config = self._default_config()
        config['project_id'] = click.prompt('GCP project ID')
        config['region'] = click.prompt('Cloud Run region', default='us-central1')
        config['artifact_registry']['location'] = click.prompt('Artifact Registry location', default=config['region'])
        config['artifact_registry']['repository'] = click.prompt('Artifact Registry Docker repository')
        config['service_defaults']['service_account'] = click.prompt('Cloud Run service account (optional)', default='', show_default=False)
        config['service_defaults']['vpc_connector'] = click.prompt('Cloud Run VPC connector (optional)', default='', show_default=False)
        config['service_defaults']['ingress'] = click.prompt('Cloud Run ingress', default='INGRESS_TRAFFIC_ALL')
        self._validate_changes(config)
        return config

    def _read_config_file(self):
        if not os.path.exists(self.config_file):
            return {}
        try:
            with open(self.config_file) as fp:
                return json.load(fp)
        except ValueError:
            raise UnrecoverableException('Unable to parse GCP environment configuration JSON.')

    def _write_config_file(self, configurations):
        if self.environment and self.environment in configurations:
            self._validate_changes(configurations[self.environment])
        config_dir = os.path.dirname(self.config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(self.config_file, 'w') as fp:
            json.dump(configurations, fp, indent=4, sort_keys=True)
            fp.write('\n')

    def _default_config(self):
        return {
            'project_id': '',
            'region': 'us-central1',
            'artifact_registry': {
                'location': 'us-central1',
                'repository': ''
            },
            'service_defaults': {
                'cpu': '1',
                'memory': '512Mi',
                'concurrency': 80,
                'service_account': '',
                'vpc_connector': '',
                'ingress': 'INGRESS_TRAFFIC_ALL'
            }
        }

    def _validate_changes(self, configuration):
        errors = []
        for key in ['project_id', 'region', 'artifact_registry', 'service_defaults']:
            if key not in configuration:
                errors.append('Missing required GCP config key: ' + key)
        artifact_registry = configuration.get('artifact_registry', {})
        for key in ['location', 'repository']:
            if not artifact_registry.get(key):
                errors.append('Missing required Artifact Registry config key: ' + key)
        service_defaults = configuration.get('service_defaults', {})
        if not configuration.get('project_id'):
            errors.append('project_id is required')
        if not configuration.get('region'):
            errors.append('region is required')
        if service_defaults.get('concurrency') is not None and not isinstance(service_defaults.get('concurrency'), int):
            errors.append('service_defaults.concurrency must be an integer')
        if service_defaults.get('ingress') and service_defaults.get('ingress') not in VALID_INGRESS_VALUES:
            errors.append('service_defaults.ingress must be one of ' + ', '.join(VALID_INGRESS_VALUES))
        if errors:
            raise UnrecoverableException('\n'.join(errors))
        return True
