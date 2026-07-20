from cloudlift.config.azure_environment_configuration import AzureEnvironmentConfiguration
from cloudlift.config.azure_service_configuration import AzureServiceConfiguration
from cloudlift.deployment.azure_container_apps_client import AzureContainerAppsClient
from cloudlift.config.logging import log_bold


class AzureServiceCreator(object):
    def __init__(self, name, environment, container_apps_client_class=AzureContainerAppsClient):
        self.name = name
        self.environment = environment
        self.container_apps_client_class = container_apps_client_class
        self.service_configuration = AzureServiceConfiguration(self.name, self.environment)

    def create(self):
        log_bold('Initiating Azure Container App service creation')
        self.service_configuration.edit_config()
        self._apply(image=self._placeholder_image())

    def update(self):
        log_bold('Starting to update Azure Container App service')
        self.service_configuration.edit_config()
        self._apply(image=self._placeholder_image())

    def _apply(self, image):
        environment_config = AzureEnvironmentConfiguration(self.environment).get_config()[self.environment]
        service_config = self.service_configuration.get_config()
        apps_client = self.container_apps_client_class(environment_config['subscription_id'])
        for container_app_name, container_app_config in service_config.get('services', {}).items():
            apps_client.create_or_update_app(
                environment_config,
                container_app_name,
                container_app_config,
                image
            )

    def _placeholder_image(self):
        environment_config = AzureEnvironmentConfiguration(self.environment).get_config()[self.environment]
        return '{}/{}:latest'.format(
            environment_config['container_registry_login_server'],
            self.name + '-repo'
        )
