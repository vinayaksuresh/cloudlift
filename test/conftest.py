import os

import pytest
import moto


if not hasattr(moto, 'mock_dynamodb2'):
    moto.mock_dynamodb2 = moto.mock_aws

if not hasattr(moto, 'mock_ssm'):
    moto.mock_ssm = moto.mock_aws


def pytest_addoption(parser):
    parser.addoption(
        '--keep-resources',
        action='store_true',
        default=False,
        help='retain cloud resources created by integration tests',
    )


@pytest.fixture(scope='session', autouse=True)
def test_aws_credentials():
    os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'
    os.environ['AWS_SECURITY_TOKEN'] = 'testing'
    os.environ['AWS_SESSION_TOKEN'] = 'testing'
    os.environ['AWS_DEFAULT_REGION'] = 'ap-south-1'


@pytest.fixture
def keep_resources(request):
    return request.config.getoption('--keep-resources')


def pytest_collection_modifyitems(config, items):
    if os.environ.get('CLOUDLIFT_RUN_AWS_INTEGRATION'):
        return
    skip_integration = pytest.mark.skip(
        reason='requires live AWS, Docker, and deployed service HTTP access'
    )
    for item in items:
        if item.fspath.basename == 'test_cloudlift.py':
            item.add_marker(skip_integration)
