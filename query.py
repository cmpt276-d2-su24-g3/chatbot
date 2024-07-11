import boto3
from boto3.dynamodb.conditions import Key
from langchain.tools import tool


@tool
async def query_dynamodb(
    origin: str = None,
    destination: str = None,
    table_name: str = None,
    latest: bool = True,
    start_time: str = None,
    end_time: str = None,
) -> str:
    """
    Queries AWS DynamoDB tables for latency data between AWS regions or regions and locations.

    Parameters:
    `origin` (str): AWS region code for the origin.
    `destination` (str): AWS region code or city name for the destination.
    `table_name` (str): Name of the DynamoDB table to query.
    `latest` (bool): Set to True for the latest ping data, or False for historical data. Defaults to True.
    `start_time` (str): ISO 8601 formatted string (required if `latest` is False).
    `end_time` (str): ISO 8601 formatted string (required if `latest` is False).

    Returns:
    `str`: A string representation of the query results, or an error message.

    Tables Available:

    `R2R-Table`: Contains data about the ping between AWS regions.
    `R2L-Table`: Contains data about the ping between AWS regions and locations.
    """
    dynamodb = boto3.resource("dynamodb")

    table = dynamodb.Table(table_name)
    key_conditions = Key("origin").eq(origin) & Key(
        "destination#timestamp"
    ).begins_with(f"{destination}#")

    try:
        filter_expression = None
        if latest is False:
            if start_time and end_time:
                filter_expression = Key("timestamp").between(start_time, end_time)
            elif start_time:
                filter_expression = Key("timestamp").gte(start_time)
            elif end_time:
                filter_expression = Key("timestamp").lte(end_time)

        if filter_expression:
            response = table.query(
                KeyConditionExpression=key_conditions,
                FilterExpression=filter_expression,
            )
        else:
            response = table.query(
                KeyConditionExpression=key_conditions,
                ScanIndexForward=False,
                Limit=1,
            )

        if response["Items"]:
            return str(response["Items"])
        else:
            if start_time and end_time:
                return f"No ping data recorded between {origin} and {destination} from {start_time} to {end_time}."
            elif start_time:
                return f"No ping data recorded between {origin} and {destination} after {start_time}."
            elif end_time:
                return f"No ping data recorded between {origin} and {destination} before {end_time}."

            return f"No ping data recorded between {origin} and {destination}."

    except Exception as e:
        return f"Error querying DynamoDB: {e}"
