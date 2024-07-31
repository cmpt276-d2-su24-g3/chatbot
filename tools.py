import boto3
import requests
from boto3.dynamodb.conditions import Attr, Key
from langchain.tools import tool
from langchain_community.document_loaders import UnstructuredURLLoader
from langchain_community.tools import DuckDuckGoSearchResults
from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

from prompts import *
from timezone import unix_to_iso_8601


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

    key_conditions = Key("origin").eq(source_region) & Key(
        "destination#timestamp"
    ).begins_with(destination + "#")

    filter_expression = Attr("destination").eq(destination)
    if latest is False:
        if time_lower_bound and time_upper_bound:
            filter_expression &= Attr("timestamp").between(
                time_lower_bound, time_upper_bound
            )
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
        return str(e)


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
        return str(e)


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
        return str(e)


@tool
async def get_aws_health() -> str:
    """
    Fetches the current AWS health incidents JSON and announcements JSON from the specified URLs.

    Returns:
        str: A string indicating the result of the requests:
            - If an error occurs during any request, returns a string describing the error.
            - If both JSONs are empty, returns "There are no current health incidents or announcements reported by AWS."
            - If the JSONs contain data, returns the JSON data as a string.
    """
    try:
        health_response = requests.get(
            "https://health.aws.amazon.com/public/currentevents",
            timeout=10,
        )
        health_response.raise_for_status()
        health_data = health_response.json()

        announcement_response = requests.get(
            "https://health.aws.amazon.com/public/announcement",
            timeout=10,
        )
        announcement_response.raise_for_status()
        announcement_data = announcement_response.json()

        results = {"health_incidents": health_data, "announcements": announcement_data}

        if not health_data and not announcement_data:
            return "There are no current health incidents or announcements reported by AWS."
        return str(results)
    except (requests.Timeout, requests.RequestException) as e:
        return str(e)


@tool
async def get_aws_health_history(start_time: str, end_time: str) -> str:
    """
    Fetches AWS health history incidents within the specified time frame.

    Parameters:
        start_time (str): The start of the time frame in ISO 8601 format.
        end_time (str): The end of the time frame in ISO 8601 format.

    Returns:
        str: A JSON string representing the filtered events within the time frame.
    """
    try:
        response = requests.get(
            "https://history-events-us-west-2-prod.s3.amazonaws.com/historyevents.json",
            timeout=10,
        )
        response.raise_for_status()
        history_data = response.json()
    except (requests.Timeout, requests.RequestException) as e:
        return str(e)

    filtered_history = {}

    for region, events in history_data.items():
        filtered_events = []
        for event in events:
            event["date"] = await unix_to_iso_8601(event["date"])
            if start_time <= event["date"] <= end_time:
                for log in event.get("event_log", []):
                    log["timestamp"] = await unix_to_iso_8601(log["timestamp"])
                filtered_events.append(event)

        if filtered_events:
            filtered_history[region] = filtered_events

    if filtered_history:
        return str(filtered_history)
    else:
        return AWS_HEALTH_NO_HISTORY


@tool
async def get_available_services(region_name: str) -> str:
    """
    Checks and lists all services available in a given AWS region.

    Parameters:
    region_name (str): The AWS region to check.

    Returns:
    str: A string listing all available services in the region.
    """
    try:
        session = boto3.Session(region_name=region_name)
        available_services = session.get_available_services()

        result = ", ".join(available_services)
        result += f"\nTotal {len(available_services)} avaliable."

        return result
    except Exception as e:
        return str(e)


@tool
async def search_duckduckgo(query: str) -> str:
    """
    Conducts a search using the DuckDuckGo API.

    Parameters:
    query (str): The search query.

    Returns:
    str: A JSON-like string representation of the search results.
    """
    wrapper = DuckDuckGoSearchAPIWrapper(safesearch="strict", max_results=10)
    search = DuckDuckGoSearchResults(api_wrapper=wrapper)

    try:
        results = await search.ainvoke(query)
        return str(results)
    except Exception as e:
        return str(e)


@tool
async def url_loader(url: str) -> str:
    """
    Loads and retrieves the content of a given URL. Takes one url at a time.

    Parameters:
    url (str): The URL of the web page to load and retrieve content from.

    Returns:
    str: The content of the web page as a string.
    """
    try:
        loader = UnstructuredURLLoader(urls=[url])
        data = loader.load()

        return str(data[0].page_content)
    except Exception as e:
        return str(e)
