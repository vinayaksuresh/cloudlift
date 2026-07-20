import subprocess

from stringcase import spinalcase

from cloudlift.deployment.ecr_client import get_container_tool
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_intent


class AzureContainerRegistryClient(object):
    def __init__(self, name, environment_config, version=None, build_args=None, working_dir='.'):
        self.name = name
        self.environment_config = environment_config
        self.version = version
        self.build_args = build_args or {}
        self.working_dir = working_dir
        self.container_tool = get_container_tool()

    def build_and_push_image(self):
        self._ensure_version()
        local_image = '{}:{}'.format(spinalcase(self.name), self.version)
        remote_image = '{}:{}'.format(self.image_repository, self.version)
        self._build_image(local_image)
        self._push_image(local_image, remote_image)
        return remote_image

    @property
    def image_repository(self):
        return '{}/{}'.format(
            self.environment_config['container_registry_login_server'],
            self.name + '-repo'
        )

    def _ensure_version(self):
        if self.version:
            return
        dirty = subprocess.check_output(['git', 'status', '--short']).decode('utf-8')
        if dirty:
            self.version = 'dirty'
        else:
            self.version = subprocess.check_output(
                ['git', 'rev-list', '-n', '1', 'HEAD']
            ).strip().decode('utf-8')

    def _build_image(self, image_name):
        log_bold('Building container image ' + image_name)
        command = [self.container_tool, 'build', '-t', image_name]
        for key, value in self.build_args.items():
            command.extend(['--build-arg', '{}={}'.format(key, value)])
        command.append(self.working_dir)
        subprocess.check_call(command)

    def _push_image(self, local_image, remote_image):
        registry_name = self.environment_config['container_registry_name']
        try:
            subprocess.check_call(['az', 'acr', 'login', '--name', registry_name])
            subprocess.check_call([self.container_tool, 'tag', local_image, remote_image])
            subprocess.check_call([self.container_tool, 'push', remote_image])
            log_intent('Pushed the image ({}) to ACR successfully.'.format(local_image))
        except Exception as exc:
            raise UnrecoverableException('Unable to push image to Azure Container Registry. {}'.format(exc))
