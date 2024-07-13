import boto3
from boto3.dynamodb.conditions import Attr, Key
from langchain.tools import tool

from prompts import DYNAMODB_QUERY_ERROR, PING_NOT_RECORDED_ERROR


@tool
async def query_dynamodb(
    source_region: str = None,
    destination: str = None,
    table_name: str = None,
    latest: bool = True,
    start_time: str = None,
    end_time: str = None,
) -> str:
    """
    Queries AWS DynamoDB tables for latency data between AWS regions or regions and locations.

    Parameters:
    `source_region` (str): AWS region code for the source region.
    `destination` (str): AWS region code or city name for the destination.
    `table_name` (str): Name of the DynamoDB table to query.
    `latest` (bool): Set to True for the latest ping data, or False for historical data. Defaults to True.
    `start_time` (str): ISO 8601 formatted string (required if `latest` is False).
    `end_time` (str): ISO 8601 formatted string (required if `latest` is False).

    Returns:
    `str`: A string representation of the query results, or an error message.

    Tables Available:

    `R2R-Table`: Contains data about the ping between AWS regions.
    `R2L-Table`: Contains data about the ping between AWS regions and locations. NOT available for now.
    """
    dynamodb = boto3.resource("dynamodb")

    table = dynamodb.Table(table_name)
    key_conditions = Key("source_region").eq(source_region)

    try:
        filter_expression = Attr("destination").eq(destination)

        if latest is False:
            if start_time and end_time:
                key_conditions &= Key("timestamp").between(start_time, end_time)
            elif start_time:
                key_conditions &= Key("timestamp").gte(start_time)
            elif end_time:
                key_conditions &= Key("timestamp").lte(end_time)

        if latest is False:
            response = table.query(
                KeyConditionExpression=key_conditions,
                FilterExpression=filter_expression,
            )
        else:
            response = table.query(
                KeyConditionExpression=key_conditions,
                FilterExpression=filter_expression,
                ScanIndexForward=False,
                Limit=1,
            )

        if response["Items"]:
            return str(response["Items"])
        else:
            if start_time and end_time:
                return PING_NOT_RECORDED_ERROR["between"].format(
                    source_region, destination, start_time, end_time
                )
            elif start_time:
                return PING_NOT_RECORDED_ERROR["after"].format(
                    source_region, destination, start_time
                )
            elif end_time:
                return PING_NOT_RECORDED_ERROR["before"].format(
                    source_region, destination, end_time
                )

            return PING_NOT_RECORDED_ERROR["default"].format(source_region, destination)

    except Exception as e:
        return DYNAMODB_QUERY_ERROR.format(e)
