from cloudlift.config.azure_environment_configuration import AzureEnvironmentConfiguration
from cloudlift.config.logging import log_bold
from cloudlift.exceptions import UnrecoverableException


class AzureEnvironmentCreator(object):
    def __init__(self, environment, credential=None, resource_client=None,
                 container_registry_client=None, keyvault_client=None,
                 container_apps_client=None):
        self.environment = environment
        self.credential = credential
        self.resource_client = resource_client
        self.container_registry_client = container_registry_client
        self.keyvault_client = keyvault_client
        self.container_apps_client = container_apps_client
        self.environment_configuration = AzureEnvironmentConfiguration(environment)

    def run(self):
        self.environment_configuration.update_config()
        config = self.environment_configuration.get_config()[self.environment]
        log_bold('Creating or updating Azure resources for {}'.format(self.environment))
        self._ensure_resource_group(config)
        self._ensure_container_registry(config)
        self._ensure_key_vault(config)
        self._ensure_container_apps_environment(config)
        self.environment_configuration.set_config({self.environment: config})

    def run_update(self, update_ecs_agents=False):
        if update_ecs_agents:
            raise UnrecoverableException('ECS agent updates are AWS-only.')
        self.run()

    def _ensure_resource_group(self, config):
        client = self.resource_client or self._build_resource_client(config)
        return client.resource_groups.create_or_update(
            config['resource_group'],
            {'location': config['location'], 'tags': {'cloudlift_provider': 'azure'}}
        )

    def _ensure_container_registry(self, config):
        client = self.container_registry_client or self._build_container_registry_client(config)
        registry = client.registries.begin_create(
            config['resource_group'],
            config['container_registry_name'],
            {
                'location': config['location'],
                'sku': {'name': 'Basic'},
                'admin_user_enabled': False,
                'tags': {'cloudlift_provider': 'azure'}
            }
        )
        if hasattr(registry, 'result'):
            registry = registry.result()
        config['container_registry_login_server'] = getattr(
            registry,
            'login_server',
            config.get('container_registry_login_server')
        )
        return registry

    def _ensure_key_vault(self, config):
        client = self.keyvault_client or self._build_keyvault_client(config)
        vault = client.vaults.begin_create_or_update(
            config['resource_group'],
            config['key_vault_name'],
            {
                'location': config['location'],
                'properties': {
                    'tenant_id': config.get('tenant_id'),
                    'sku': {'family': 'A', 'name': 'standard'},
                    'access_policies': []
                },
                'tags': {'cloudlift_provider': 'azure'}
            }
        )
        if hasattr(vault, 'result'):
            vault = vault.result()
        config['key_vault_uri'] = getattr(vault, 'properties', {}).get('vault_uri') if isinstance(getattr(vault, 'properties', {}), dict) else config.get('key_vault_uri')
        return vault

    def _ensure_container_apps_environment(self, config):
        client = self.container_apps_client or self._build_container_apps_client(config)
        managed_environment = client.managed_environments.begin_create_or_update(
            config['resource_group'],
            config['container_apps_environment_name'],
            {
                'location': config['location'],
                'tags': {'cloudlift_provider': 'azure'},
                'properties': {}
            }
        )
        if hasattr(managed_environment, 'result'):
            managed_environment = managed_environment.result()
        config['container_apps_environment_id'] = getattr(
            managed_environment,
            'id',
            config.get('container_apps_environment_id')
        )
        return managed_environment

    def _credential(self):
        if self.credential:
            return self.credential
        try:
            from azure.identity import DefaultAzureCredential
            self.credential = DefaultAzureCredential()
            return self.credential
        except Exception as exc:
            raise UnrecoverableException('Unable to create Azure credential. {}'.format(exc))

    def _build_resource_client(self, config):
        from azure.mgmt.resource import ResourceManagementClient
        return ResourceManagementClient(self._credential(), config['subscription_id'])

    def _build_container_registry_client(self, config):
        from azure.mgmt.containerregistry import ContainerRegistryManagementClient
        return ContainerRegistryManagementClient(self._credential(), config['subscription_id'])

    def _build_keyvault_client(self, config):
        from azure.mgmt.keyvault import KeyVaultManagementClient
        return KeyVaultManagementClient(self._credential(), config['subscription_id'])

    def _build_container_apps_client(self, config):
        from azure.mgmt.appcontainers import ContainerAppsAPIClient
        return ContainerAppsAPIClient(self._credential(), config['subscription_id'])
