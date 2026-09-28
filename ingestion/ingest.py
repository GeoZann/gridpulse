"""Fetch ENTSO-E day-ahead prices and persist the raw response in MongoDB."""

import argparse
import os
from datetime import date, datetime, timedelta, timezone

from dotenv import load_dotenv

from ingestion.entsoe_client import DOCUMENT_TYPE, LOCAL_TZ, fetch_day_ahead_prices, get_greece_domain, request_window


def store_raw_response(collection, target_day: date, raw_xml: str) -> dict:
    """Upsert one raw response per document type, zone, and local date."""
    local_start, local_end = request_window(target_day)
    domain = get_greece_domain()
    record_id = f"{DOCUMENT_TYPE}:{domain}:{target_day.isoformat()}"
    document = {
        "_id": record_id,
        "document_type": DOCUMENT_TYPE,
        "bidding_zone": domain,
        "requested_date": target_day.isoformat(),
        "requested_period": {
            "start_utc": local_start.astimezone(timezone.utc),
            "end_utc": local_end.astimezone(timezone.utc),
            "timezone": str(LOCAL_TZ),
        },
        "fetched_at": datetime.now(timezone.utc),
        "raw_xml": raw_xml,
    }
    collection.replace_one({"_id": record_id}, document, upsert=True)
    return document


def get_api_token() -> str:
    token = os.environ.get("ENTSOE_API_TOKEN")
    if not token:
        raise RuntimeError("Set ENTSOE_API_TOKEN in your environment or .env file.")
    return token


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="Athens calendar date (YYYY-MM-DD); defaults to yesterday")
    args = parser.parse_args()
    target_day = args.date or (datetime.now(LOCAL_TZ).date() - timedelta(days=1))

    from pymongo import MongoClient

    token = get_api_token()
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    mongo_db = os.environ.get("MONGO_DB", "gridpulse")
    raw_xml = fetch_day_ahead_prices(token, target_day)

    with MongoClient(mongo_uri) as client:
        document = store_raw_response(client[mongo_db]["raw_entsoe_responses"], target_day, raw_xml)

    print(f"Stored {document['_id']} ({len(raw_xml)} XML characters) in MongoDB {mongo_db}.")


if __name__ == "__main__":
    main()
