import subprocess

from stringcase import spinalcase

from cloudlift.deployment.ecr_client import get_container_tool
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_intent


class ArtifactRegistryClient(object):
    def __init__(self, service_name, project_id, location, repository,
                 build_args=None, working_dir='.', container_tool=None):
        self.service_name = service_name
        self.project_id = project_id
        self.location = location
        self.repository = repository
        self.build_args = build_args
        self.working_dir = working_dir
        self.container_tool = container_tool or get_container_tool()

    def build_and_upload_image(self, version):
        version = version or self._find_commit_sha_or_dirty()
        local_image = spinalcase(self.service_name) + ':' + version
        image_uri = self.image_uri(version)
        self._build_image(local_image)
        self._push_image(local_image, image_uri)
        return image_uri

    def image_uri(self, version):
        return '%s-docker.pkg.dev/%s/%s/%s:%s' % (
            self.location,
            self.project_id,
            self.repository,
            spinalcase(self.service_name),
            version,
        )

    def _build_image(self, image_name):
        log_bold('Building container image ' + image_name)
        self._check_call(self._build_command(image_name), shell=True)
        log_bold('Built ' + image_name)

    def _build_command(self, image_name):
        if self.build_args is None:
            return '%s build -t %s %s' % (self.container_tool, image_name, self.working_dir)
        build_args_command_fragment = []
        for key, value in self.build_args.items():
            build_args_command_fragment.append(' --build-arg ' + '='.join((key, value)))
        return '%s build -t %s%s %s' % (
            self.container_tool,
            image_name,
            ''.join(build_args_command_fragment),
            self.working_dir,
        )

    def _push_image(self, local_name, image_uri):
        host = '%s-docker.pkg.dev' % self.location
        try:
            self._check_call([self.container_tool, 'tag', local_name, image_uri])
        except UnrecoverableException:
            raise UnrecoverableException('Local image was not found.')
        self._check_call(['gcloud', 'auth', 'configure-docker', host, '--quiet'])
        self._check_call([self.container_tool, 'push', image_uri])
        self._check_call([self.container_tool, 'rmi', image_uri])
        log_intent('Pushed the image (' + local_name + ') to Artifact Registry successfully.')

    def _find_commit_sha_or_dirty(self):
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
        except Exception:
            raise UnrecoverableException('Commit SHA not found.')

    def _check_call(self, command, shell=False):
        try:
            subprocess.check_call(command, shell=shell)
        except subprocess.CalledProcessError as error:
            raise UnrecoverableException('Artifact Registry image command failed: %s' % error)
