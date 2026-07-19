import functools

import boto3
import click
import dictdiffer
from botocore.exceptions import ClientError, NoCredentialsError

from cloudlift.config import highlight_production, highlight_user_account_details
from cloudlift.config import print_parameter_changes
from cloudlift.config.pre_flight import check_stack_exists
from cloudlift.deployment.configs import deduce_name
from cloudlift.deployment import EnvironmentCreator, editor
from cloudlift.config.logging import log_err, log_warning
from cloudlift.deployment.deployer import read_config
from cloudlift.deployment.service_creator import ServiceCreator
from cloudlift.deployment.service_information_fetcher import ServiceInformationFetcher
from cloudlift.deployment.service_updater import ServiceUpdater
from cloudlift.deployment.task_definition_creator import TaskDefinitionCreator
from cloudlift.gcp import CloudRunServiceUpdater, GcpEnvironmentConfiguration, GcpSecretManagerStore
from cloudlift.session import SessionCreator
from cloudlift.version import VERSION
from cloudlift.exceptions import UnrecoverableException


def _require_aws_connection(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            boto3.client('cloudformation')
        except (ClientError, NoCredentialsError):
            log_err("Could not connect to AWS!")
            log_err("Ensure AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY & \
AWS_DEFAULT_REGION env vars are set OR run 'aws configure'")
            exit(1)
        return func(*args, **kwargs)

    return wrapper


def _require_environment(func):
    @click.option('--environment', '-e', prompt='environment',
                  help='environment')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if kwargs['environment'] == 'production':
            highlight_production()
        highlight_user_account_details()
        return func(*args, **kwargs)

    return wrapper


def _require_gcp_environment(func):
    @click.option('--environment', '-e', prompt='environment',
                  help='GCP environment')
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
        Cloudlift launches dockerized services to AWS ECS and GCP Cloud Run.
    """
    pass


@cli.command(help="Create a new service. This can contain multiple \
ECS services")
@_require_aws_connection
@_require_environment
@_require_name
def create_service(name, environment):
    check_stack_exists(name, environment, "create")
    ServiceCreator(name, environment).create()


@cli.command(help="Update existing service.")
@_require_aws_connection
@_require_environment
@_require_name
def update_service(name, environment):
    check_stack_exists(name, environment, "update")
    ServiceCreator(name, environment).update()


@cli.command(help="Create a new environment")
@_require_aws_connection
@click.option('--environment', '-e', prompt='environment',
              help='environment')
def create_environment(environment):
    EnvironmentCreator(environment).run()


@cli.command(help="Update environment")
@_require_aws_connection
@_require_environment
@click.option('--update_ecs_agents',
              is_flag=True,
              help='Update ECS container agents')
def update_environment(environment, update_ecs_agents):
    EnvironmentCreator(environment).run_update(update_ecs_agents)


@cli.command(help="Command used to create or update the configuration \
in parameter store")
@_require_aws_connection
@_require_name
@_require_environment
def edit_config(name, environment):
    editor.edit_config(name, environment)


@cli.command()
@_require_aws_connection
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def deploy_service(name, environment, version, build_arg):
    ServiceUpdater(name, environment, None, version, dict(build_arg)).run()


@cli.command()
@_require_aws_connection
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def create_task_definition(name, environment, version, build_arg):
    TaskDefinitionCreator(name, environment, version, dict(build_arg)).create()


@cli.command()
@_require_aws_connection
@_require_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def update_task_definition(name, environment, version, build_arg):
    TaskDefinitionCreator(name, environment, version, dict(build_arg)).update()


@cli.command()
@_require_aws_connection
@click.option('--local_tag', help='Commit sha for image to be uploaded')
@click.option('--additional_tags', default=[], multiple=True,
              help='Additional tags for the image apart from commit SHA')
@_require_name
def upload_to_ecr(name, local_tag, additional_tags):
    ServiceUpdater(name, '', '', local_tag).upload_image(additional_tags)


@cli.command(help="Get commit information of currently deployed code \
from commit hash")
@_require_aws_connection
@_require_environment
@_require_name
@click.option('--short', '-s', is_flag=True,
              help='Pass this when you just need the version tag')
def get_version(name, environment, short):
    ServiceInformationFetcher(name, environment).get_version(short)


@cli.command(help="Start SSH session in instance running a current \
service task")
@_require_aws_connection
@_require_environment
@_require_name
@click.option('--mfa', help='MFA code')
@click.option('--component', help='nested service name')
def start_session(name, environment, mfa, component):
    SessionCreator(name, environment).start_session(mfa, component)


@cli.command(name='gcp_create_environment', help='Create or update a GCP Cloud Run environment configuration')
@_require_gcp_environment
@click.option('--project-id', prompt='GCP project ID', help='GCP project ID')
@click.option('--region', prompt='Cloud Run region', default='us-central1', help='Cloud Run region')
@click.option('--artifact-location', prompt='Artifact Registry location', default='us', help='Artifact Registry location')
@click.option('--artifact-repository', prompt='Artifact Registry Docker repository', help='Artifact Registry repository')
@click.option('--service-account', default=None, help='Cloud Run service account email')
@click.option('--vpc-connector', default=None, help='Cloud Run VPC connector resource name')
@click.option('--ingress', default=None, help='Cloud Run ingress enum')
def gcp_create_environment(environment, project_id, region, artifact_location,
                           artifact_repository, service_account,
                           vpc_connector, ingress):
    GcpEnvironmentConfiguration(environment).create_or_update_config(
        project_id=project_id,
        region=region,
        artifact_registry_location=artifact_location,
        artifact_registry_repository=artifact_repository,
        service_account=service_account,
        vpc_connector=vpc_connector,
        ingress=ingress,
    )


@cli.command(name='gcp_edit_config', help='Create or update service secrets in GCP Secret Manager')
@_require_name
@_require_gcp_environment
def gcp_edit_config(name, environment):
    config = GcpEnvironmentConfiguration(environment).get_config()
    secret_store = GcpSecretManagerStore(name, environment, config['project_id'])
    env_config_strings = secret_store.get_existing_config_as_string()
    edited_config_content = click.edit(str(env_config_strings))
    if edited_config_content is None:
        log_warning('No changes made, exiting.')
        return
    differences = list(dictdiffer.diff(
        read_config(env_config_strings),
        read_config(edited_config_content)
    ))
    if not differences:
        log_warning('No changes made, exiting.')
    else:
        print_parameter_changes(differences)
        if click.confirm('Do you want update the GCP config?'):
            secret_store.set_config(differences)
        else:
            log_warning('Changes aborted.')


@cli.command(name='gcp_deploy_service', help='Build, push, and deploy a service to GCP Cloud Run')
@_require_gcp_environment
@_require_name
@click.option('--version', default=None,
              help='local image version tag')
@click.option("--build-arg", type=(str, str), multiple=True, help="These args are passed to docker build command "
                                                                  "as --build-args. Supports multiple.\
                                                                   Please leave space between name and value" )
def gcp_deploy_service(name, environment, version, build_arg):
    CloudRunServiceUpdater(name, environment, None, version, dict(build_arg)).run()


if __name__ == '__main__':
    cli()
