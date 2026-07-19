from cloudlift.exceptions import UnrecoverableException


SUPPORTED_PROVIDERS = ("aws", "gcp")


def get_provider(provider_name="aws"):
    provider_name = (provider_name or "aws").lower()
    if provider_name == "aws":
        from cloudlift.providers.aws import AwsProvider
        return AwsProvider()
    if provider_name == "gcp":
        from cloudlift.providers.gcp.provider import GcpProvider
        return GcpProvider()
    raise UnrecoverableException(
        "Unsupported provider '{}'. Supported providers: {}".format(
            provider_name,
            ", ".join(SUPPORTED_PROVIDERS),
        )
    )
