import functools

import click

from cloudlift.config import highlight_production, highlight_user_account_details
from cloudlift.deployment import editor
from cloudlift.deployment.configs import deduce_name
from cloudlift.config.logging import log_err
from cloudlift.exceptions import UnrecoverableException
from cloudlift.providers import get_provider
from cloudlift.version import VERSION


def _require_environment(func):
    @click.option('--environment', '-e', prompt='environment',
                  help='environment')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def _require_name(func):
    @click.option('--name', help='Your service name, give the name of \
repo')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if kwargs['name'] is None:
            kwargs['name'] = deduce_name(None)
        return func(*args, **kwargs)

    return wrapper


def _provider_option(func):
    return click.option('--provider', default='aws', show_default=True,
                        type=click.Choice(['aws', 'gcp']),
                        help='Cloud provider to target')(func)


def _gcp_environment_options(func):
    options = [
        click.option('--config-path', help='Path to the local GCP environment config JSON'),
        click.option('--project-id', help='GCP project ID'),
        click.option('--location', help='GCP region or zone containing the GKE cluster'),
        click.option('--cluster-name', help='Existing GKE cluster name'),
        click.option('--namespace', help='Kubernetes namespace for workloads'),
        click.option('--artifact-registry-repository', help='Artifact Registry Docker repository'),
        click.option('--service-account', help='Kubernetes service account for pods'),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _gcp_runtime_options(func):
    options = [
        click.option('--config-path', help='Path to the local GCP environment config JSON'),
        click.option('--container-port', default=80, show_default=True,
                     help='Container port for GKE services'),
        click.option('--replicas', default=1, show_default=True,
                     help='Replica count for GKE deployments'),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _before_provider_command(environment, provider):
    if environment == 'production':
        highlight_production()
    if provider == 'aws':
        highlight_user_account_details()


class CommandWrapper(click.Group):
    def __call__(self, *args, **kwargs):
        return self.main(*args, **kwargs)

    def main(self, *args, **kwargs):
        try:
            return super(CommandWrapper, self).main(*args, **kwargs)
        except UnrecoverableException as e:
            log_err(e.value)
            exit(1)


@click.group(cls=CommandWrapper)
@click.version_option(version=VERSION, prog_name="cloudlift")
def cli():
    """
        Cloudlift launches dockerized services on AWS ECS and GCP GKE.
    """
    pass


@cli.command(help="Create a new service. This can contain multiple ECS services on AWS or a GKE Deployment/Service on GCP")
@_provider_option
@_gcp_runtime_options
@_require_environment
@_require_name
@click.option('--version', default=None, help='image version tag for GCP')
def create_service(name, environment, provider, config_path, container_port, replicas, version):
    _before_provider_command(environment, provider)
    get_provider(provider).create_service(
        name,
        environment,
        config_path=config_path,
        container_port=container_port,
        replicas=replicas,
        version=version,
    )


@cli.command(help="Update existing service.")
@_provider_option
@_gcp_runtime_options
@_require_environment
@_require_name
@click.option('--version', default=None, help='image version tag for GCP')
def update_service(name, environment, provider, config_path, container_port, replicas, version):
    _before_provider_command(environment, provider)
    get_provider(provider).update_service(
        name,
        environment,
        config_path=config_path,
        container_port=container_port,
        replicas=replicas,
        version=version,
    )


@cli.command(help="Create a new environment")
@_provider_option
@_gcp_environment_options
@click.option('--environment', '-e', prompt='environment',
              help='environment')
def create_environment(environment, provider, config_path, project_id, location,
                       cluster_name, namespace, artifact_registry_repository,
                       service_account):
    _before_provider_command(environment, provider)
    get_provider(provider).create_environment(
        environment,
        config_path=config_path,
        project_id=project_id,
        location=location,
        cluster_name=cluster_name,
        namespace=namespace,
        artifact_registry_repository=artifact_registry_repository,
        service_account=service_account,
    )


@cli.command(help="Update environment")
@_provider_option
@_gcp_environment_options
@_require_environment
@click.option('--update_ecs_agents',
              is_flag=True,
              help='Update ECS container agents')
def update_environment(environment, provider, config_path, project_id, location,
                       cluster_name, namespace, artifact_registry_repository,
                       service_account, update_ecs_agents):
    _before_provider_command(environment, provider)
    get_provider(provider).update_environment(
        environment,
        update_ecs_agents=update_ecs_agents,
        config_path=config_path,
        project_id=project_id,
        location=location,
        cluster_name=cluster_name,
        namespace=namespace,
        artifact_registry_repository=artifact_registry_repository,
        service_account=service_account,
    )


@cli.command(help="Command used to create or update the configuration in parameter store")
@_require_name
@_require_environment
def edit_config(name, environment):
    _before_provider_command(environment, 'aws')
    editor.edit_config(name, environment)


@cli.command()
@_provider_option
@click.option('--config-path', help='Path to the local GCP environment config JSON')
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def deploy_service(name, environment, provider, config_path, version, build_arg):
    _before_provider_command(environment, provider)
    get_provider(provider).deploy_service(
        name,
        environment,
        version=version,
        build_args=dict(build_arg),
        config_path=config_path,
    )


@cli.command()
@_provider_option
@click.option('--config-path', help='Path to the local GCP environment config JSON')
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def create_task_definition(name, environment, provider, config_path, version, build_arg):
    _before_provider_command(environment, provider)
    get_provider(provider).create_task_definition(
        name,
        environment,
        version=version,
        build_args=dict(build_arg),
        config_path=config_path,
    )


@cli.command()
@_provider_option
@click.option('--config-path', help='Path to the local GCP environment config JSON')
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def update_task_definition(name, environment, provider, config_path, version, build_arg):
    _before_provider_command(environment, provider)
    get_provider(provider).update_task_definition(
        name,
        environment,
        version=version,
        build_args=dict(build_arg),
        config_path=config_path,
    )


@cli.command(help="Upload a local image to ECR, or Artifact Registry with --provider gcp")
@_provider_option
@click.option('--environment', '-e', default='', help='environment (required for --provider gcp)')
@click.option('--config-path', help='Path to the local GCP environment config JSON')
@click.option('--local_tag', help='Commit sha for image to be uploaded')
@click.option('--additional_tags', default=[], multiple=True,
              help='Additional tags for the image apart from commit SHA')
@_require_name
def upload_to_ecr(name, provider, environment, config_path, local_tag, additional_tags):
    if environment:
        _before_provider_command(environment, provider)
    get_provider(provider).upload_image(
        name,
        environment=environment,
        local_tag=local_tag,
        additional_tags=additional_tags,
        config_path=config_path,
    )


@cli.command(help="Get commit information of currently deployed code from commit hash")
@_provider_option
@click.option('--config-path', help='Path to the local GCP environment config JSON')
@_require_environment
@_require_name
@click.option('--short', '-s', is_flag=True,
              help='Pass this when you just need the version tag')
def get_version(name, environment, provider, config_path, short):
    _before_provider_command(environment, provider)
    get_provider(provider).get_version(
        name,
        environment,
        short=short,
        config_path=config_path,
    )


@cli.command(help="Start SSH session in instance running a current service task (AWS only)")
@_require_environment
@_require_name
@click.option('--mfa', help='MFA code')
@click.option('--component', help='nested service name')
def start_session(name, environment, mfa, component):
    _before_provider_command(environment, 'aws')
    get_provider('aws').start_session(name, environment, mfa, component)


if __name__ == '__main__':
    cli()
