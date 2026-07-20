import os

import moto

os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')


if not hasattr(moto, 'mock_dynamodb2'):
    moto.mock_dynamodb2 = moto.mock_aws

if not hasattr(moto, 'mock_ssm'):
    moto.mock_ssm = moto.mock_aws
