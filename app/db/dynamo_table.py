# What it does: The one DynamoDB table Operator uses: connection and creation.
#   Key: pk = record kind (e.g. "leads"), sk = record id. On-demand billing.
#   Env: DYNAMODB_TABLE (default "operator"), AWS_REGION (default us-east-1),
#   DYNAMODB_ENDPOINT_URL (set locally -> DynamoDB Local, e.g. http://localhost:8001; unset on AWS).
#   CLI: python -m app.db.dynamo_table create — creates the table if missing (no-op if it exists).
# When it runs: On every DynamoDB record read/write (table()); create on every local DynamoDB start.
# What calls it: app/db/records_dynamo.py; sh/dynamo-local.sh (create); tests/test_records_dynamo.py.
import os
import sys
from functools import lru_cache

import boto3


def table_name() -> str:
    return os.environ.get("DYNAMODB_TABLE", "operator")


@lru_cache(maxsize=None)
def _resource(endpoint_url: str | None, region: str):
    if endpoint_url:
        # DynamoDB Local accepts any credentials; fixed ones so local runs need no AWS login.
        return boto3.resource("dynamodb", endpoint_url=endpoint_url, region_name=region,
                              aws_access_key_id="local", aws_secret_access_key="local")
    return boto3.resource("dynamodb", region_name=region)


def resource():
    return _resource(os.environ.get("DYNAMODB_ENDPOINT_URL") or None, os.environ.get("AWS_REGION", "us-east-1"))


def table():
    return resource().Table(table_name())


def create() -> bool:
    """Creates the table if it doesn't exist. Returns True if it was created."""
    client = resource().meta.client
    if table_name() in client.list_tables()["TableNames"]:
        return False
    client.create_table(
        TableName=table_name(),
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"},
                              {"AttributeName": "sk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name())
    return True


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    if sys.argv[1:] != ["create"]:
        sys.exit("Usage: python -m app.db.dynamo_table create")
    print(f"Table {table_name()}: {'created' if create() else 'already exists'}")
