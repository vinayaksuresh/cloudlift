"""Compatibility hooks for the repository test suite."""

import os

import pytest
import moto

if not hasattr(moto, 'mock_dynamodb2'):
    moto.mock_dynamodb2 = moto.mock_aws

if not hasattr(moto, 'mock_ssm'):
    moto.mock_ssm = moto.mock_aws


@pytest.fixture(scope='session', autouse=True)
def test_aws_credentials():
    os.environ.setdefault('AWS_ACCESS_KEY_ID', 'testing')
    os.environ.setdefault('AWS_SECRET_ACCESS_KEY', 'testing')
    os.environ.setdefault('AWS_SECURITY_TOKEN', 'testing')
    os.environ.setdefault('AWS_SESSION_TOKEN', 'testing')
    os.environ.setdefault('AWS_DEFAULT_REGION', 'ap-south-1')


@pytest.fixture(autouse=True)
def aws_test_compatibility(monkeypatch):
    region = os.environ.get('AWS_DEFAULT_REGION', 'ap-south-1')
    monkeypatch.setattr('cloudlift.config.pre_flight.check_sns_topic_exists', lambda topic_name, environment: True)
    monkeypatch.setattr('cloudlift.config.environment_configuration.check_sns_topic_exists', lambda topic_name, environment: True)
    monkeypatch.setattr('cloudlift.config.region.get_region_for_environment', lambda environment: region)
    monkeypatch.setattr('cloudlift.config.get_region_for_environment', lambda environment: region)
    monkeypatch.setattr('cloudlift.deployment.service_updater.get_region_for_environment', lambda environment: region)


@pytest.fixture
def keep_resources():
    return False
