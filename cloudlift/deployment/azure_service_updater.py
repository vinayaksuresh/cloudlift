import os

from cloudlift.config.azure_environment_configuration import AzureEnvironmentConfiguration
from cloudlift.config.azure_service_configuration import AzureServiceConfiguration
from cloudlift.deployment.azure_container_apps_client import AzureContainerAppsClient
from cloudlift.deployment.azure_container_registry_client import AzureContainerRegistryClient
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_intent, log_warning


class AzureServiceUpdater(object):
    def __init__(self, name, environment, env_sample_file, version=None,
                 build_args=None, working_dir='.', registry_client_class=AzureContainerRegistryClient,
                 container_apps_client_class=AzureContainerAppsClient):
        self.name = name
        self.environment = environment
        self.env_sample_file = env_sample_file or './env.sample'
        self.version = version
        self.build_args = build_args
        self.working_dir = working_dir
        self.registry_client_class = registry_client_class
        self.container_apps_client_class = container_apps_client_class

    def run(self):
        if not os.path.exists(self.env_sample_file):
            raise UnrecoverableException('env.sample not found. Exiting.')
        environment_config = AzureEnvironmentConfiguration(self.environment).get_config()[self.environment]
        service_config = AzureServiceConfiguration(self.name, self.environment).get_config()
        image = self.registry_client_class(
            self.name,
            environment_config,
            self.version,
            self.build_args,
            self.working_dir
        ).build_and_push_image()
        log_intent('name: {} | environment: {} | image: {}'.format(
            self.name,
            self.environment,
            image
        ))
        log_bold('Updating Azure Container App revision')
        self._deploy_services(environment_config, service_config, image)

    def upload_image(self, additional_tags):
        log_warning('Additional Azure image tags are not implemented; pushing the selected version only.')
        environment_config = AzureEnvironmentConfiguration(self.environment).get_config()[self.environment]
        return self.registry_client_class(
            self.name,
            environment_config,
            self.version,
            self.build_args,
            self.working_dir
        ).build_and_push_image()

    def _deploy_services(self, environment_config, service_config, image):
        apps_client = self.container_apps_client_class(environment_config['subscription_id'])
        for container_app_name, container_app_config in service_config.get('services', {}).items():
            apps_client.create_or_update_app(
                environment_config,
                container_app_name,
                container_app_config,
                image
            )
