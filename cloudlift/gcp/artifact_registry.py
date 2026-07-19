import re
import subprocess
from shutil import which

from cloudlift.config.logging import log_bold, log_intent
from cloudlift.exceptions import UnrecoverableException


def to_gcp_name(value):
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')


class ArtifactRegistryClient(object):
    def __init__(self, service_name, project_id, location, repository,
                 version=None, build_args=None, working_dir='.', container_tool=None):
        self.service_name = service_name
        self.project_id = project_id
        self.location = location
        self.repository = repository
        self.build_args = build_args or {}
        self.working_dir = working_dir
        self.container_tool = container_tool or self._get_container_tool()
        self.version = version or self._determine_version()

    def build_and_upload_image(self):
        local_image_name = self.local_image_name
        remote_image_uri = self.image_uri
        try:
            self._build_image(local_image_name)
            self._tag_image(local_image_name, remote_image_uri)
            self._login_to_artifact_registry()
            self._push_image(remote_image_uri)
            self._remove_remote_tag(remote_image_uri)
        except subprocess.CalledProcessError as error:
            raise UnrecoverableException('Artifact Registry image build or push failed: %s' % error)
        return remote_image_uri

    @property
    def registry_host(self):
        return '%s-docker.pkg.dev' % self.location

    @property
    def image_uri(self):
        return '%s/%s/%s/%s:%s' % (
            self.registry_host,
            self.project_id,
            self.repository,
            to_gcp_name(self.service_name),
            self.version,
        )

    @property
    def local_image_name(self):
        return '%s:%s' % (to_gcp_name(self.service_name), self.version)

    def _build_image(self, image_name):
        log_bold('Building container image ' + image_name)
        command = [self.container_tool, 'build', '-t', image_name]
        for key, value in self.build_args.items():
            command.extend(['--build-arg', '='.join((key, value))])
        command.append(self.working_dir)
        subprocess.check_call(command)
        log_bold('Built ' + image_name)

    def _tag_image(self, local_image_name, remote_image_uri):
        subprocess.check_call([self.container_tool, 'tag', local_image_name, remote_image_uri])

    def _login_to_artifact_registry(self):
        log_intent('Configuring Docker credentials for Artifact Registry')
        subprocess.check_call([
            'gcloud', 'auth', 'configure-docker', self.registry_host, '--quiet'
        ])

    def _push_image(self, remote_image_uri):
        subprocess.check_call([self.container_tool, 'push', remote_image_uri])
        log_intent('Pushed the image to Artifact Registry successfully.')

    def _remove_remote_tag(self, remote_image_uri):
        subprocess.check_call([self.container_tool, 'rmi', remote_image_uri])

    def _determine_version(self):
        dirty = subprocess.check_output(['git', 'status', '--short']).decode('utf-8')
        if dirty:
            log_intent('Version parameter was not provided. Determined version to be dirty based on current status')
            return 'dirty'
        try:
            commit_sha = subprocess.check_output(
                ['git', 'rev-list', '-n', '1', 'HEAD']
            ).strip().decode('utf-8')
            log_intent('Version parameter was not provided. Determined version to be ' + commit_sha)
            return commit_sha
        except subprocess.CalledProcessError:
            raise UnrecoverableException('Commit SHA not found.')

    def _get_container_tool(self):
        tool = which('podman') or which('docker')
        if tool is None:
            raise UnrecoverableException('Podman or Docker not installed')
        log_intent('Using %s as container tool' % tool)
        return tool
