import boto3
from boto3.dynamodb.conditions import Attr, Key
from langchain.tools import tool

from prompts import (
    DYNAMODB_QUERY_ERROR,
    NOT_ENOUGH_ENTRY_ERROR,
    PING_NOT_RECORDED_ERROR,
)


@tool
async def get_pings(
    source_region: str,
    destination: str,
    table_name: str,
    latest: bool = True,
    start_time: str = None,
    end_time: str = None,
) -> str:
    """
    Queries AWS DynamoDB tables for latency data between AWS regions or regions and locations.
    Time range required if `latest` is False.

    Parameters:
    `source_region` (str): AWS region code for the source region.
    `destination` (str): AWS region code when r2r or city name for the destination when r2l.
    `table_name` (str): Name of the DynamoDB table to query.
    `latest` (bool): Set to True for the latest ping data, or False for historical data. Defaults to True.
    `start_time` (str): ISO 8601 formatted string. UTC.
    `end_time` (str): ISO 8601 formatted string. UTC.

    Returns:
    `str`: A string representation of the query results, or an error message.
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
            return response["Items"]
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


@tool
def get_nth_ping_given_source(
    source_region: str,
    table_name: str,
    n: int,
    start_time: str,
    end_time: str,
    highest: bool = False,
):
    """
    Query for the nth lowest or highest ping destination from a given source region within a specified time range.

    Parameters:
    `source_region` (str): AWS region code for the source region.
    `table_name` (str): Name of the DynamoDB table to query.
    `n` (int): The rank of the ping to find.
    `start_time` (str): ISO 8601 formatted string. UTC.
    `end_time` (str): ISO 8601 formatted string. UTC.
    `highest` (bool): Set to True to find the nth highest ping, or False to find the nth lowest ping. Defaults to False.

    Returns:
    `str`: A string representation of the query result, or an error message.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    key_conditions = Key("source_region").eq(source_region)
    if start_time:
        key_conditions &= Key("timestamp").gte(start_time)
    if end_time:
        key_conditions &= Key("timestamp").lte(end_time)

    try:
        response = table.query(
            KeyConditionExpression=key_conditions,
            ScanIndexForward=False,  # Sort by timestamp descending to get the latest records first
        )

        if "Items" in response:
            latest_pings = {}
            for item in response["Items"]:
                destination = item["destination"]
                if destination not in latest_pings:
                    latest_pings[destination] = item
                else:
                    current_timestamp = latest_pings[destination]["timestamp"]
                    if item["timestamp"] > current_timestamp:
                        latest_pings[destination] = item

            items = sorted(
                latest_pings.values(),
                key=lambda x: float(x["latency"]),
                reverse=highest,
            )
            if len(items) >= n:
                return items[n - 1]
            else:
                return NOT_ENOUGH_ENTRY_ERROR.format(n, len(items))
        else:
            return PING_NOT_RECORDED_ERROR["single"].format(source_region)

    except Exception as e:
        return DYNAMODB_QUERY_ERROR.format(e)


@tool
def get_nth_ping_given_destination(
    destination: str,
    table_name: str,
    n: int,
    start_time: str,
    end_time: str,
    highest: bool=False,
):
    """
    Query for the nth lowest or highest ping source to a given destination within a specified time range.

    Parameters:
    `destination` (str): AWS region code or city name for the destination.
    `table_name` (str): Name of the DynamoDB table to query.
    `n` (int): The rank of the ping to find.
    `start_time` (str): ISO 8601 formatted string. UTC.
    `end_time` (str): ISO 8601 formatted string. UTC.
    `highest` (bool): Set to True to find the nth highest ping, or False to find the nth lowest ping. Defaults to False.

    Returns:
    `str`: A string representation of the query result, or an error message.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    try:
        filter_expression = Attr("destination").eq(destination)
        if start_time:
            filter_expression &= Attr("timestamp").gte(start_time)
        if end_time:
            filter_expression &= Attr("timestamp").lte(end_time)

        response = table.scan(FilterExpression=filter_expression)

        if "Items" in response:
            latest_pings = {}
            for item in response["Items"]:
                source_region = item["source_region"]
                if source_region not in latest_pings:
                    latest_pings[source_region] = item
                else:
                    current_timestamp = latest_pings[source_region]["timestamp"]
                    if item["timestamp"] > current_timestamp:
                        latest_pings[source_region] = item

            items = sorted(
                latest_pings.values(),
                key=lambda x: float(x["latency"]),
                reverse=highest,
            )
            if len(items) >= n:
                return items[n - 1]
            else:
                return NOT_ENOUGH_ENTRY_ERROR.format(n, len(items))
        else:
            return PING_NOT_RECORDED_ERROR["single"].format(destination)

    except Exception as e:
        return DYNAMODB_QUERY_ERROR.format(e)
