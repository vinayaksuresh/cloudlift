import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from cloudlift.exceptions import UnrecoverableException

AWS_PROVIDER = 'aws'
AZURE_PROVIDER = 'azure'
SUPPORTED_PROVIDERS = (AWS_PROVIDER, AZURE_PROVIDER)


class ProviderImplementation(object):
    def __init__(self, provider, environment_creator, service_creator,
                 service_updater, task_definition_creator=None,
                 service_information_fetcher=None, session_creator=None,
                 credential_check=None):
        self.provider = provider
        self.environment_creator = environment_creator
        self.service_creator = service_creator
        self.service_updater = service_updater
        self.task_definition_creator = task_definition_creator
        self.service_information_fetcher = service_information_fetcher
        self.session_creator = session_creator
        self.credential_check = credential_check

    def ensure_credentials(self):
        if self.credential_check:
            self.credential_check()

    def require_aws_only(self, command_name):
        if self.provider != AWS_PROVIDER:
            raise UnrecoverableException(
                "`{}` is AWS-only until {} support is implemented.".format(
                    command_name,
                    self.provider
                )
            )


class ProviderResolver(object):
    @classmethod
    def validate(cls, provider):
        provider = (provider or AWS_PROVIDER).lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise UnrecoverableException(
                "Unsupported provider `{}`. Supported providers are: {}".format(
                    provider,
                    ', '.join(SUPPORTED_PROVIDERS)
                )
            )
        return provider

    @classmethod
    def resolve(cls, provider=None):
        provider = cls.validate(provider)
        if provider == AWS_PROVIDER:
            return cls._aws_implementation()
        return cls._azure_implementation()

    @classmethod
    def from_environment_config(cls, environment):
        """
        Resolve the provider recorded for an existing environment. AWS remains
        the default for older DynamoDB records that do not have a provider key.
        """
        try:
            from cloudlift.config.environment_configuration import EnvironmentConfiguration
            config = EnvironmentConfiguration(environment).get_config()
            environment_config = config.get(environment, {})
            return cls.resolve(environment_config.get('provider', AWS_PROVIDER))
        except UnrecoverableException:
            # If the AWS-backed record is not present, try Azure-native storage.
            # This keeps Azure environments out of DynamoDB while still allowing
            # existing AWS environments without a provider field to resolve to AWS.
            try:
                from cloudlift.config.azure_environment_configuration import AzureEnvironmentConfiguration
                config = AzureEnvironmentConfiguration(environment).get_config()
                environment_config = config.get(environment, {})
                return cls.resolve(environment_config.get('provider'))
            except Exception:
                raise

    @classmethod
    def _aws_implementation(cls):
        from cloudlift.deployment.environment_creator import EnvironmentCreator
        from cloudlift.deployment.service_creator import ServiceCreator
        from cloudlift.deployment.service_updater import ServiceUpdater
        from cloudlift.deployment.task_definition_creator import TaskDefinitionCreator
        from cloudlift.deployment.service_information_fetcher import ServiceInformationFetcher
        from cloudlift.session.session_creator import SessionCreator
        return ProviderImplementation(
            AWS_PROVIDER,
            EnvironmentCreator,
            ServiceCreator,
            ServiceUpdater,
            task_definition_creator=TaskDefinitionCreator,
            service_information_fetcher=ServiceInformationFetcher,
            session_creator=SessionCreator,
            credential_check=check_aws_credentials
        )

    @classmethod
    def _azure_implementation(cls):
        from cloudlift.deployment.azure_environment_creator import AzureEnvironmentCreator
        from cloudlift.deployment.azure_service_creator import AzureServiceCreator
        from cloudlift.deployment.azure_service_updater import AzureServiceUpdater
        return ProviderImplementation(
            AZURE_PROVIDER,
            AzureEnvironmentCreator,
            AzureServiceCreator,
            AzureServiceUpdater,
            credential_check=check_azure_credentials
        )


def check_aws_credentials():
    try:
        boto3.client('sts').get_caller_identity()
    except (ClientError, NoCredentialsError):
        raise UnrecoverableException(
            "Could not connect to AWS! Ensure AWS_ACCESS_KEY_ID, "
            "AWS_SECRET_ACCESS_KEY & AWS_DEFAULT_REGION env vars are set OR "
            "run 'aws configure'."
        )


def check_azure_credentials():
    try:
        from azure.identity import DefaultAzureCredential
        credential = DefaultAzureCredential()
        credential.get_token('https://management.azure.com/.default')
    except Exception as exc:
        raise UnrecoverableException(
            "Could not authenticate with Azure. Run `az login` or configure "
            "an Azure SDK credential before using the Azure provider. {}".format(exc)
        )
