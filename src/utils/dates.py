"""Date parsing utilities."""

from datetime import datetime


def parse_date_param(date_str: str, end_of_day: bool = False) -> datetime:
    """Parse a date string in YYYY-MM-DD or ISO-8601 format.

    Args:
        date_str: Date string to parse.
        end_of_day: If True and input is YYYY-MM-DD, set time to 23:59:59.

    Returns:
        Parsed datetime.

    Raises:
        ValueError: If the format is invalid.
    """
    if "T" in date_str:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt
