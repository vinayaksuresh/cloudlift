from cloudlift.exceptions import UnrecoverableException


class AzureContainerAppsClient(object):
    def __init__(self, subscription_id, credential=None, container_apps_client=None):
        self.subscription_id = subscription_id
        self.client = container_apps_client or self._build_client(credential)

    def create_or_update_app(self, environment_config, service_name, service_config, image):
        resource_group = environment_config['resource_group']
        app_name = self._container_app_name(service_name)
        payload = self._build_container_app_payload(
            environment_config,
            service_name,
            service_config,
            image
        )
        poller = self.client.container_apps.begin_create_or_update(
            resource_group,
            app_name,
            payload
        )
        if hasattr(poller, 'result'):
            return poller.result()
        return poller

    def _build_container_app_payload(self, environment_config, service_name, service_config, image):
        command = service_config.get('command')
        container = {
            'name': self._container_app_name(service_name),
            'image': image,
            'resources': {
                'cpu': float(service_config.get('cpu', service_config.get('cpu_reservation', 0.5))),
                'memory': str(service_config.get('memory', self._memory_from_reservation(service_config)))
            },
            'env': self._environment_variables(service_config)
        }
        if command is not None:
            container['command'] = [command] if isinstance(command, str) else command

        http_interface = service_config.get('http_interface', {})
        ingress = None
        if http_interface:
            ingress = {
                'external': not http_interface.get('internal', False),
                'targetPort': int(http_interface.get('container_port', 80)),
                'transport': 'auto'
            }
            if http_interface.get('hostnames'):
                ingress['customDomains'] = [
                    {'name': hostname} for hostname in http_interface.get('hostnames', [])
                ]

        probes = []
        if http_interface.get('health_check_path'):
            probes.append({
                'type': 'Liveness',
                'httpGet': {
                    'path': http_interface['health_check_path'],
                    'port': int(http_interface.get('container_port', 80))
                }
            })
            container['probes'] = probes

        template = {
            'containers': [container],
            'scale': {
                'minReplicas': int(service_config.get('min_replicas', 1)),
                'maxReplicas': int(service_config.get('max_replicas', 1))
            }
        }
        configuration = {
            'activeRevisionsMode': 'Single',
            'registries': [{
                'server': environment_config['container_registry_login_server'],
                'identity': 'system'
            }]
        }
        if ingress:
            configuration['ingress'] = ingress

        return {
            'location': environment_config['location'],
            'tags': self._tags(environment_config, service_name),
            'identity': {'type': 'SystemAssigned'},
            'properties': {
                'managedEnvironmentId': environment_config.get('container_apps_environment_id'),
                'configuration': configuration,
                'template': template
            }
        }

    def _environment_variables(self, service_config):
        env = []
        for key, value in service_config.get('env', {}).items():
            if isinstance(value, dict) and value.get('secretRef'):
                env.append({'name': key, 'secretRef': value['secretRef']})
            else:
                env.append({'name': key, 'value': str(value)})
        for key, value in service_config.get('secrets', {}).items():
            env.append({'name': key, 'secretRef': value})
        return env

    def _tags(self, environment_config, service_name):
        tags = dict(environment_config.get('tags', {}))
        tags.update({
            'cloudlift_provider': 'azure',
            'environment': environment_config.get('environment_name', ''),
            'service': service_name
        })
        return tags

    def _memory_from_reservation(self, service_config):
        memory_reservation = service_config.get('memory_reservation')
        if memory_reservation:
            return '{}Mi'.format(int(memory_reservation))
        fargate = service_config.get('fargate', {})
        if fargate.get('memory'):
            return '{}Mi'.format(int(fargate['memory']))
        return '1Gi'

    def _container_app_name(self, service_name):
        return service_name.lower().replace('_', '-')

    def _build_client(self, credential):
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.appcontainers import ContainerAppsAPIClient
            return ContainerAppsAPIClient(credential or DefaultAzureCredential(), self.subscription_id)
        except Exception as exc:
            raise UnrecoverableException(
                'Unable to create Azure Container Apps client. {}'.format(exc)
            )
