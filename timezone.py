from datetime import datetime
import pytz

async def convert_to_utc(iso8601_string):
    """
    Converts an ISO 8601 formatted string to UTC.

    Parameters:
    `iso8601_string` (str): ISO 8601 formatted date-time string.

    Returns:
    `str`: The converted UTC date-time string in ISO 8601 format.
    """
    dt = datetime.fromisoformat(iso8601_string)
    dt_utc = dt.astimezone(pytz.utc)
    return dt_utc.isoformat()
