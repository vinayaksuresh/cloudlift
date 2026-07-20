import functools

import click

from cloudlift.config import highlight_production
from cloudlift.config.provider import ProviderResolver, AWS_PROVIDER
from cloudlift.config.pre_flight import check_stack_exists
from cloudlift.deployment.configs import deduce_name
from cloudlift.deployment import editor
from cloudlift.config.logging import log_err
from cloudlift.version import VERSION
from cloudlift.exceptions import UnrecoverableException


def _require_environment(func):
    @click.option('--environment', '-e', prompt='environment',
                  help='environment')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if kwargs['environment'] == 'production':
            highlight_production()
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


class CommandWrapper(click.Group):
    def __call__(self, *args, **kwargs):
        try:
            return self.main(*args, **kwargs)
        except UnrecoverableException as e:
            log_err(e.value)
            exit(1)


@click.group(cls=CommandWrapper)
@click.version_option(version=VERSION, prog_name="cloudlift")
def cli():
    """
        Cloudlift launches dockerized services in AWS ECS and Azure Container Apps.
    """
    pass


def _provider_for_environment(environment):
    provider = ProviderResolver.from_environment_config(environment)
    provider.ensure_credentials()
    return provider


def _provider_for_create(provider_name):
    provider = ProviderResolver.resolve(provider_name)
    provider.ensure_credentials()
    return provider


@cli.command(help="Create a new service. This can contain multiple services")
@_require_environment
@_require_name
def create_service(name, environment):
    provider = _provider_for_environment(environment)
    if provider.provider == AWS_PROVIDER:
        check_stack_exists(name, environment, "create")
    provider.service_creator(name, environment).create()


@cli.command(help="Update existing service.")
@_require_environment
@_require_name
def update_service(name, environment):
    provider = _provider_for_environment(environment)
    if provider.provider == AWS_PROVIDER:
        check_stack_exists(name, environment, "update")
    provider.service_creator(name, environment).update()


@cli.command(help="Create a new environment")
@click.option('--environment', '-e', prompt='environment',
              help='environment')
@click.option('--provider', default=AWS_PROVIDER, show_default=True,
              type=click.Choice(['aws', 'azure']),
              help='cloud provider for the environment')
def create_environment(environment, provider):
    implementation = _provider_for_create(provider)
    implementation.environment_creator(environment).run()


@cli.command(help="Update environment")
@_require_environment
@click.option('--update_ecs_agents',
              is_flag=True,
              help='Update ECS container agents')
def update_environment(environment, update_ecs_agents):
    provider = _provider_for_environment(environment)
    provider.environment_creator(environment).run_update(update_ecs_agents)


@cli.command(help="Command used to create or update the configuration \
in parameter store")
@_require_name
@_require_environment
def edit_config(name, environment):
    provider = _provider_for_environment(environment)
    provider.require_aws_only('edit_config')
    editor.edit_config(name, environment)


@cli.command()
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def deploy_service(name, environment, version, build_arg):
    provider = _provider_for_environment(environment)
    provider.service_updater(name, environment, None, version, dict(build_arg)).run()


@cli.command()
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def create_task_definition(name, environment, version, build_arg):
    provider = _provider_for_environment(environment)
    provider.require_aws_only('create_task_definition')
    provider.task_definition_creator(name, environment, version, dict(build_arg)).create()


@cli.command()
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def update_task_definition(name, environment, version, build_arg):
    provider = _provider_for_environment(environment)
    provider.require_aws_only('update_task_definition')
    provider.task_definition_creator(name, environment, version, dict(build_arg)).update()


@cli.command()
@click.option('--local_tag', help='Commit sha for image to be uploaded')
@click.option('--additional_tags', default=[], multiple=True,
              help='Additional tags for the image apart from commit SHA')
@_require_name
def upload_to_ecr(name, local_tag, additional_tags):
    provider = _provider_for_create(AWS_PROVIDER)
    provider.service_updater(name, '', '', local_tag).upload_image(additional_tags)


@cli.command(help="Get commit information of currently deployed code \
from commit hash")
@_require_environment
@_require_name
@click.option('--short', '-s', is_flag=True,
              help='Pass this when you just need the version tag')
def get_version(name, environment, short):
    provider = _provider_for_environment(environment)
    provider.require_aws_only('get_version')
    provider.service_information_fetcher(name, environment).get_version(short)


@cli.command(help="Start SSH session in instance running a current \
service task")
@_require_environment
@_require_name
@click.option('--mfa', help='MFA code')
@click.option('--component', help='nested service name')
def start_session(name, environment, mfa, component):
    provider = _provider_for_environment(environment)
    provider.require_aws_only('start_session')
    provider.session_creator(name, environment).start_session(mfa, component)


if __name__ == '__main__':
    cli()
