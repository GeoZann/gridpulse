"""
GridPulse — Step 1: "Hello World" for the ENTSO-E API.

Goal: successfully pull ONE day of Greek day-ahead electricity prices
and print them. Nothing fancy yet — no MongoDB, no Spark, no Docker.
Just prove the API connection works end to end.

Setup:
1. pip install requests
2. Set your ENTSO-E security token as an environment variable:
     export ENTSOE_API_TOKEN="your-token-here"      (Linux/Mac)
     setx ENTSOE_API_TOKEN "your-token-here"          (Windows)
   (Get the token from your account settings at transparency.entsoe.eu,
   after your "Restful API access" request has been approved.)
3. Run: python entsoe_hello_world.py
"""

import os
import sys
from datetime import date, timedelta
from xml.etree import ElementTree as ET

import requests

# --- Configuration ---------------------------------------------------------

API_URL = "https://web-api.tp.entsoe.eu/api"

# Greece bidding zone (Hellenic TSO). Double-check this against the live
# "Area" list in the ENTSO-E API guide if something looks off.
GREECE_DOMAIN = "10YGR-HTSO-----Y"

# The ENTSO-E XML responses use these namespaces — needed to parse the tree.
NAMESPACES = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}


def get_api_token() -> str:
    token = os.environ.get("ENTSOE_API_TOKEN")
    if not token:
        sys.exit(
            "ERROR: Set the ENTSOE_API_TOKEN environment variable first "
            "(see the setup instructions at the top of this file)."
        )
    return token


def fetch_day_ahead_prices(token: str, target_day: date) -> str:
    """
    Calls the ENTSO-E RESTful API for day-ahead prices (documentType A44)
    for Greece, for the 24 hours of `target_day`.

    ENTSO-E expects periods in UTC, formatted as YYYYMMDDHHmm.
    We request from midnight of target_day to midnight of the next day.
    """
    period_start = target_day.strftime("%Y%m%d") + "0000"
    period_end = (target_day + timedelta(days=1)).strftime("%Y%m%d") + "0000"

    params = {
        "securityToken": token,
        "documentType": "A44",       # Price document
        "in_Domain": GREECE_DOMAIN,
        "out_Domain": GREECE_DOMAIN,
        "periodStart": period_start,
        "periodEnd": period_end,
    }

    response = requests.get(API_URL, params=params, timeout=30)

    if response.status_code != 200:
        sys.exit(
            f"ERROR: API returned status {response.status_code}\n"
            f"Response body:\n{response.text[:1000]}"
        )

    return response.text


def parse_prices(xml_text: str) -> list[tuple[int, float]]:
    """
    Extracts (position, price) pairs from the raw XML.
    `position` is the hour-of-day index (1-24), `price` is EUR/MWh.
    """
    root = ET.fromstring(xml_text)
    results = []

    for point in root.findall(".//ns:Point", NAMESPACES):
        position = point.find("ns:position", NAMESPACES)
        price = point.find("ns:price.amount", NAMESPACES)
        if position is not None and price is not None:
            results.append((int(position.text), float(price.text)))

    return sorted(results)


def main():
    token = get_api_token()

    # Yesterday is usually the safest bet — today's day-ahead prices are
    # only published once the market has cleared, which can be late.
    target_day = date.today() - timedelta(days=1)

    print(f"Fetching Greek day-ahead prices for {target_day.isoformat()}...")
    xml_text = fetch_day_ahead_prices(token, target_day)
    prices = parse_prices(xml_text)

    if not prices:
        print("No price points found. Print the raw XML below to debug:")
        print(xml_text[:2000])
        return

    print(f"\nGot {len(prices)} hourly prices for {target_day.isoformat()}:\n")
    for hour, price in prices:
        print(f"  Hour {hour:>2}: {price:>7.2f} EUR/MWh")

    avg_price = sum(p for _, p in prices) / len(prices)
    print(f"\nAverage price: {avg_price:.2f} EUR/MWh")


if __name__ == "__main__":
    main()