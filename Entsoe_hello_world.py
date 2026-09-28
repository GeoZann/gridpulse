"""
GridPulse — Step 1 (v2): "Hello World" for the ENTSO-E API.

Fixes over v1:
- Requests the window in Greek local time (Europe/Athens), converted to UTC.
- Reads each TimeSeries/Period separately, using its own start time and
  resolution (PT15M or PT60M) instead of assuming hourly data.
- Expands omitted points: ENTSO-E skips a position when its price equals
  the previous one (curve type A03), so we forward-fill them.
- Converts every point to a real timestamp and keeps only the target day.

Setup:
1. pip install requests tzdata      (tzdata is needed for time zones on Windows)
2. Set ENTSOE_API_TOKEN as an environment variable (open a NEW terminal after setx).
3. Run: python entsoe_hello_world_v2.py
"""

import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()

import requests

API_URL = "https://web-api.tp.entsoe.eu/api"
GREECE_DOMAIN = os.environ.get("ENTSOE_DOMAIN", "10YGR-HTSO-----Y")
LOCAL_TZ = ZoneInfo("Europe/Athens")
NAMESPACES = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}


def get_api_token() -> str:
    token = os.environ.get("ENTSOE_API_TOKEN")
    if not token:
        sys.exit("ERROR: Set the ENTSOE_API_TOKEN environment variable first.")
    return token


def to_api_time(dt: datetime) -> str:
    """ENTSO-E wants UTC, formatted as YYYYMMDDHHmm."""
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def fetch_day_ahead_prices(token: str, target_day: date) -> str:
    """Request exactly the local (Athens) day: local midnight -> next local midnight."""
    local_start = datetime(target_day.year, target_day.month, target_day.day, tzinfo=LOCAL_TZ)
    local_end = local_start + timedelta(days=1)  # calendar-day step; DST handled by zoneinfo below
    local_end = datetime(local_end.year, local_end.month, local_end.day, tzinfo=LOCAL_TZ)

    params = {
        "securityToken": token,
        "documentType": "A44",  # day-ahead prices
        "in_Domain": GREECE_DOMAIN,
        "out_Domain": GREECE_DOMAIN,
        "periodStart": to_api_time(local_start),
        "periodEnd": to_api_time(local_end),
    }
    response = requests.get(API_URL, params=params, timeout=30)
    if response.status_code != 200:
        sys.exit(f"ERROR: API returned {response.status_code}\n{response.text[:1000]}")
    return response.text


def parse_resolution(text: str) -> timedelta:
    """Turns 'PT15M' / 'PT60M' / 'PT1H' into a timedelta."""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", text)
    if not match or not any(match.groups()):
        raise ValueError(f"Unsupported resolution: {text}")
    hours, minutes = (int(g) if g else 0 for g in match.groups())
    return timedelta(hours=hours, minutes=minutes)


def parse_utc(text: str) -> datetime:
    """ENTSO-E timestamps look like 2026-09-26T21:00Z."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def parse_prices(xml_text: str) -> list[tuple[datetime, float, str]]:
    """
    Returns (timestamp_utc, price_eur_mwh, resolution) for every interval,
    with omitted positions forward-filled.
    """
    root = ET.fromstring(xml_text)
    rows = []

    for series in root.findall(".//ns:TimeSeries", NAMESPACES):
        for period in series.findall("ns:Period", NAMESPACES):
            start = parse_utc(period.find("ns:timeInterval/ns:start", NAMESPACES).text)
            end = parse_utc(period.find("ns:timeInterval/ns:end", NAMESPACES).text)
            res_text = period.find("ns:resolution", NAMESPACES).text
            step = parse_resolution(res_text)
            n_positions = int((end - start) / step)

            known = {
                int(p.find("ns:position", NAMESPACES).text): float(p.find("ns:price.amount", NAMESPACES).text)
                for p in period.findall("ns:Point", NAMESPACES)
            }

            last_price = None
            for position in range(1, n_positions + 1):
                last_price = known.get(position, last_price)  # forward-fill omitted points
                if last_price is not None:
                    rows.append((start + (position - 1) * step, last_price, res_text))

    return sorted(rows)


def main():
    token = get_api_token()
    target_day = datetime.now(LOCAL_TZ).date() - timedelta(days=1)

    print(f"Fetching Greek day-ahead prices for {target_day.isoformat()} (Europe/Athens)...")
    rows = parse_prices(fetch_day_ahead_prices(token, target_day))

    # Keep only intervals that fall on the target local day (safety filter).
    rows = [(ts.astimezone(LOCAL_TZ), price, res) for ts, price, res in rows
            if ts.astimezone(LOCAL_TZ).date() == target_day]

    if not rows:
        print("No price points found for that day.")
        return

    resolutions = sorted({res for _, _, res in rows})
    print(f"Got {len(rows)} price intervals (resolution: {', '.join(resolutions)})\n")

    # Hourly averages (works for both PT15M and PT60M data).
    by_hour: dict[int, list[float]] = {}
    for ts, price, _ in rows:
        by_hour.setdefault(ts.hour, []).append(price)

    print("Hour (local)   Avg price (EUR/MWh)")
    for hour in sorted(by_hour):
        prices = by_hour[hour]
        print(f"  {hour:02d}:00        {sum(prices) / len(prices):>8.2f}")

    all_prices = [price for _, price, _ in rows]
    print(f"\nDaily average: {sum(all_prices) / len(all_prices):.2f} EUR/MWh")
    print(f"Daily min:     {min(all_prices):.2f} EUR/MWh")
    print(f"Daily max:     {max(all_prices):.2f} EUR/MWh")


if __name__ == "__main__":
    main()