import os

import moto
import pytest


os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SECURITY_TOKEN", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")


# Several legacy tests still import service-specific moto decorators that were
# removed in moto 5. Keep those tests on the repo's pinned moto version by
# aliasing them to the all-service mock.
if not hasattr(moto, "mock_dynamodb2"):
    moto.mock_dynamodb2 = moto.mock_aws
if not hasattr(moto, "mock_ssm"):
    moto.mock_ssm = moto.mock_aws


@pytest.fixture
def keep_resources(request):
    try:
        return request.config.getoption("--keep-resources")
    except ValueError:
        return False
