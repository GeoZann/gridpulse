"""Small ENTSO-E client for Greek day-ahead prices."""

import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

API_URL = "https://web-api.tp.entsoe.eu/api"
DEFAULT_GREECE_DOMAIN = "10YGR-HTSO-----Y"
LOCAL_TZ = ZoneInfo("Europe/Athens")
DOCUMENT_TYPE = "A44"


def get_greece_domain() -> str:
    return os.environ.get("ENTSOE_DOMAIN", DEFAULT_GREECE_DOMAIN)


def request_window(target_day: date) -> tuple[datetime, datetime]:
    """Return local midnights for the requested Athens calendar day."""
    start = datetime.combine(target_day, time.min, tzinfo=LOCAL_TZ)
    end = datetime.combine(target_day + timedelta(days=1), time.min, tzinfo=LOCAL_TZ)
    return start, end


def to_api_time(value: datetime) -> str:
    """Format a datetime as the UTC timestamp expected by ENTSO-E."""
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def fetch_day_ahead_prices(token: str, target_day: date) -> str:
    """Fetch the raw XML for one Greek local calendar day."""
    local_start, local_end = request_window(target_day)
    domain = get_greece_domain()
    params = {
        "securityToken": token,
        "documentType": DOCUMENT_TYPE,
        "in_Domain": domain,
        "out_Domain": domain,
        "periodStart": to_api_time(local_start),
        "periodEnd": to_api_time(local_end),
    }
    response = requests.get(API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.text
