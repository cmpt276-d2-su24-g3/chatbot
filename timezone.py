from datetime import datetime, UTC


async def convert_to_utc(iso8601_string: str) -> str:
    dt = datetime.fromisoformat(iso8601_string)
    dt_utc = dt.astimezone(UTC)
    return dt_utc.isoformat()


async def unix_to_iso_8601(unix_string: str) -> str:
    unix_timestemp = int(unix_string)
    dt = datetime.fromtimestamp(unix_timestemp, UTC)
    return dt.isoformat()
