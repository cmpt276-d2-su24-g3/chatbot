import boto3
import requests
from boto3.dynamodb.conditions import Attr, Key
from langchain.tools import tool

from prompts import *

@tool
async def get_pings(
    source_region: str,
    destination: str,
    table_name: str,
    latest: bool = True,
    time_lower_bound: str = None,
    time_upper_bound: str = None,
) -> str:
    """
    Queries AWS DynamoDB tables for latency data between AWS regions or regions and locations.
    Time range required if latest is False.

    Parameters:
    source_region (str): AWS region code for the source region.
    destination (str): AWS region code when r2r or city name for the destination when r2l.
    table_name (str): Name of the DynamoDB table to query.
    latest (bool): Set to True for the latest ping data, or False for historical data. Defaults to True.
    time_lower_bound (str): ISO 8601 formatted string. UTC.
    time_upper_bound (str): ISO 8601 formatted string. UTC.

    Returns:
    str: A string representation of the query results, or an error message.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    key_conditions = Key("origin").eq(source_region) & Key("destination#timestamp").begins_with(destination + '#')

    filter_expression = Attr("destination").eq(destination)
    if latest is False:
        if time_lower_bound and time_upper_bound:
            filter_expression &= Attr("timestamp").between(time_lower_bound, time_upper_bound)
        elif time_lower_bound:
            filter_expression &= Attr("timestamp").gte(time_lower_bound)
        elif time_upper_bound:
            filter_expression &= Attr("timestamp").lte(time_upper_bound)

    try:
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
        print(response)
        if response["Items"]:
            return str(response["Items"])
        else:
            if time_lower_bound and time_upper_bound:
                return PING_NOT_RECORDED_ERROR["between"].format(
                    source_region, destination, time_lower_bound, time_upper_bound
                )
            elif time_lower_bound:
                return PING_NOT_RECORDED_ERROR["after"].format(
                    source_region, destination, time_lower_bound
                )
            elif time_upper_bound:
                return PING_NOT_RECORDED_ERROR["before"].format(
                    source_region, destination, time_upper_bound
                )

            return PING_NOT_RECORDED_ERROR["default"].format(source_region, destination)

    except Exception as e:
        return DYNAMODB_QUERY_ERROR.format(e)


@tool
async def get_nth_ping_given_source(
    source_region: str,
    table_name: str,
    n: int,
    time_lower_bound: str,
    time_upper_bound: str,
    highest: bool = False,
):
    """
    Query for the nth lowest or highest ping destination from a given source region within a specified time range.

    Parameters:
    source_region (str): AWS region code for the source region.
    table_name (str): Name of the DynamoDB table to query.
    n (int): The rank of the ping to find.
    time_lower_bound (str): ISO 8601 formatted string. UTC.
    time_upper_bound (str): ISO 8601 formatted string. UTC.
    highest (bool): Set to True to find the nth highest ping, or False to find the nth lowest ping. Defaults to False.

    Returns:
    str: A string representation of the query result, or an error message.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    key_conditions = Key("origin").eq(source_region)

    filter_expression = Attr("timestamp").between(time_lower_bound, time_upper_bound)

    try:
        response = table.query(
            KeyConditionExpression=key_conditions,
            FilterExpression=filter_expression,
            ScanIndexForward=not highest,
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
                return str(items[n - 1])
            else:
                return NOT_ENOUGH_ENTRY_ERROR.format(n, len(items))
        else:
            return PING_NOT_RECORDED_ERROR["single"].format(source_region)

    except Exception as e:
        return DYNAMODB_QUERY_ERROR.format(e)


@tool
async def get_nth_ping_given_destination(
    destination: str,
    table_name: str,
    n: int,
    time_lower_bound: str,
    time_upper_bound: str,
    highest: bool = False,
):
    """
    Query for the nth lowest or highest ping source to a given destination within a specified time range.

    Parameters:
    destination (str): AWS region code or city name for the destination.
    table_name (str): Name of the DynamoDB table to query.
    n (int): The rank of the ping to find.
    time_lower_bound (str): ISO 8601 formatted string. UTC.
    time_upper_bound (str): ISO 8601 formatted string. UTC.
    highest (bool): Set to True to find the nth highest ping, or False to find the nth lowest ping. Defaults to False.

    Returns:
    str: A string representation of the query result, or an error message.
    """
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    try:
        scan_kwargs = {
            "FilterExpression": Attr("destination").eq(destination)
            & Attr("timestamp").between(time_lower_bound, time_upper_bound)
        }

        response = table.scan(**scan_kwargs)

        if "Items" in response:
            latest_pings = {}
            for item in response["Items"]:
                source_region = item["origin"]
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
                return str(items[n - 1])
            else:
                return NOT_ENOUGH_ENTRY_ERROR.format(n, len(items))
        else:
            return PING_NOT_RECORDED_ERROR["single"].format(destination)

    except Exception as e:
        return DYNAMODB_QUERY_ERROR.format(e)


@tool
async def get_aws_health() -> str:
    """
    Fetches the current AWS health incidents JSON from the specified URL.

    Returns:
        str: A message indicating the result of the request:
            - If an error occurs during the request, returns a message describing the error.
            - If the JSON is empty, returns "There are no current health incidents reported by AWS."
            - If the JSON contains data, returns the JSON data as a string.
    """
    try:
        response = requests.get(
            "https://health.aws.amazon.com/public/currentevents",
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if not data:
            return AWS_HEALTH_NO_INCIDENT
        return str(data)
    except requests.Timeout:
        return AWS_HEALTH_REQUEST_TIMEOUT
    except requests.RequestException as e:
        return e