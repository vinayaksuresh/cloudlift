import subprocess

from stringcase import spinalcase

from cloudlift.deployment.ecr_client import get_container_tool
from cloudlift.exceptions import UnrecoverableException
from cloudlift.config.logging import log_bold, log_intent


class ArtifactRegistryClient(object):
    """Build and push Docker images to Google Artifact Registry."""

    def __init__(self, service_name, project_id, location, repository, version=None,
                 build_args=None, working_dir='.', container_tool=None):
        self.service_name = service_name
        self.project_id = project_id
        self.location = location
        self.repository = repository
        self.version = version or self._find_commit_sha()
        self.build_args = build_args or {}
        self.working_dir = working_dir
        self.container_tool = container_tool or get_container_tool()

    def build_and_upload_image(self):
        local_image = "%s:%s" % (spinalcase(self.service_name), self.version)
        remote_image = self.image_uri
        self._build_image(local_image)
        self._push_image(local_image, remote_image)
        return remote_image

    @property
    def image_uri(self):
        return "%s-docker.pkg.dev/%s/%s/%s:%s" % (
            self.location,
            self.project_id,
            self.repository,
            spinalcase(self.service_name),
            self.version
        )

    @property
    def registry_host(self):
        return "%s-docker.pkg.dev" % self.location

    def _build_image(self, image_name):
        log_bold("Building container image " + image_name)
        self._run(self._build_command(image_name), shell=True, error="Container image build failed.")
        log_bold("Built " + image_name)

    def _build_command(self, image_name):
        build_args_command_fragment = []
        for key, value in self.build_args.items():
            build_args_command_fragment.append(" --build-arg " + "=".join((key, value)))
        return "%s build -t %s%s %s" % (
            self.container_tool,
            image_name,
            "".join(build_args_command_fragment),
            self.working_dir
        )

    def _push_image(self, local_name, remote_name):
        try:
            self._run([self.container_tool, "tag", local_name, remote_name], error="Local image was not found.")
            self._login_to_artifact_registry()
            self._run([self.container_tool, "push", remote_name], error="Artifact Registry image push failed.")
            self._run([self.container_tool, "rmi", remote_name], error="Artifact Registry image cleanup failed.")
        except UnrecoverableException:
            raise
        log_intent("Pushed the image (%s) to Artifact Registry successfully." % local_name)

    def _login_to_artifact_registry(self):
        self._run(
            ["gcloud", "auth", "configure-docker", self.registry_host, "--quiet"],
            error="Unable to configure Docker authentication for Artifact Registry."
        )

    def _find_commit_sha(self, version=None):
        try:
            version_to_find = version or "HEAD"
            return subprocess.check_output(
                ["git", "rev-list", "-n", "1", version_to_find]
            ).strip().decode("utf-8")
        except Exception:
            raise UnrecoverableException("Commit SHA not found. Given version is not a git tag, branch or commit SHA")

    def _run(self, command, shell=False, error="Command failed."):
        try:
            subprocess.check_call(command, shell=shell)
        except subprocess.CalledProcessError:
            raise UnrecoverableException(error)
