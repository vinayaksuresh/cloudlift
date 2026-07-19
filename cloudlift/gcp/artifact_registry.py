import re
import subprocess

from stringcase import spinalcase

from cloudlift.deployment.ecr_client import get_container_tool
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_intent


class ArtifactRegistryClient(object):
    def __init__(self, name, project_id, location, repository, version=None, build_args=None, working_dir='.'):
        self.name = name
        self.project_id = project_id
        self.location = location
        self.repository = repository
        self.version = version or 'latest'
        self.build_args = build_args or {}
        self.working_dir = working_dir
        self.container_tool = get_container_tool()

    def build_and_upload_image(self):
        local_image = '{}:{}'.format(self.image_name, self.version)
        remote_image = self.image_uri
        self._build_image(local_image)
        self._push_image(local_image, remote_image)
        return remote_image

    @property
    def image_uri(self):
        return '{}-docker.pkg.dev/{}/{}/{}:{}'.format(
            self.location,
            self.project_id,
            self.repository,
            self.image_name,
            self.version
        )

    @property
    def image_name(self):
        return re.sub(r'-+', '-', re.sub(r'[^a-z0-9-]', '-', spinalcase(self.name).lower())).strip('-')

    @property
    def registry_host(self):
        return '{}-docker.pkg.dev'.format(self.location)

    def _build_image(self, image_name):
        log_bold('Building container image ' + image_name)
        try:
            subprocess.check_call(self._build_command(image_name), shell=True)
        except subprocess.CalledProcessError:
            raise UnrecoverableException('Unable to build container image for GCP deployment.')
        log_bold('Built ' + image_name)

    def _build_command(self, image_name):
        build_args_command_fragment = []
        for key, value in self.build_args.items():
            build_args_command_fragment.append(' --build-arg ' + '='.join((key, value)))
        return '{} build -t {}{} {}'.format(
            self.container_tool,
            image_name,
            ''.join(build_args_command_fragment),
            self.working_dir
        )

    def _push_image(self, local_image, remote_image):
        try:
            subprocess.check_call([self.container_tool, 'tag', local_image, remote_image])
            subprocess.check_call(['gcloud', 'auth', 'configure-docker', self.registry_host, '--quiet'])
            subprocess.check_call([self.container_tool, 'push', remote_image])
            subprocess.check_call([self.container_tool, 'rmi', remote_image])
        except subprocess.CalledProcessError:
            raise UnrecoverableException('Unable to push container image to Artifact Registry.')
        log_intent('Pushed the image (' + local_image + ') to Artifact Registry successfully.')
