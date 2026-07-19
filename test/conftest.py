from moto import mock_aws
import moto


# Moto 5 removed service-specific mock decorators. Keep legacy tests working by
# exposing the old names as aliases for the all-service mock.
moto.mock_dynamodb2 = mock_aws
moto.mock_ssm = mock_aws
