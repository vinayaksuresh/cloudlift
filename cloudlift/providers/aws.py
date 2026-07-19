from cloudlift.config.pre_flight import check_stack_exists
from cloudlift.deployment import EnvironmentCreator
from cloudlift.deployment.service_creator import ServiceCreator
from cloudlift.deployment.service_information_fetcher import ServiceInformationFetcher
from cloudlift.deployment.service_updater import ServiceUpdater
from cloudlift.deployment.task_definition_creator import TaskDefinitionCreator
from cloudlift.session import SessionCreator


class AwsProvider(object):
    name = "aws"

    def create_environment(self, environment, **_kwargs):
        return EnvironmentCreator(environment).run()

    def update_environment(self, environment, update_ecs_agents=False, **_kwargs):
        return EnvironmentCreator(environment).run_update(update_ecs_agents)

    def create_service(self, name, environment, **_kwargs):
        check_stack_exists(name, environment, "create")
        return ServiceCreator(name, environment).create()

    def update_service(self, name, environment, **_kwargs):
        check_stack_exists(name, environment, "update")
        return ServiceCreator(name, environment).update()

    def deploy_service(self, name, environment, version=None, build_args=None, **_kwargs):
        return ServiceUpdater(name, environment, None, version, build_args or {}).run()

    def create_task_definition(self, name, environment, version=None, build_args=None, **_kwargs):
        return TaskDefinitionCreator(name, environment, version, build_args or {}).create()

    def update_task_definition(self, name, environment, version=None, build_args=None, **_kwargs):
        return TaskDefinitionCreator(name, environment, version, build_args or {}).update()

    def upload_image(self, name, environment="", local_tag=None, additional_tags=None, build_args=None, **_kwargs):
        return ServiceUpdater(name, environment, "", local_tag, build_args or {}).upload_image(additional_tags or [])

    def get_version(self, name, environment, short=False, **_kwargs):
        return ServiceInformationFetcher(name, environment).get_version(short)

    def start_session(self, name, environment, mfa=None, component=None, **_kwargs):
        return SessionCreator(name, environment).start_session(mfa, component)
