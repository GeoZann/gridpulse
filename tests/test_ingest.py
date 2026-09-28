import unittest
from datetime import date
from os import environ
from unittest.mock import Mock, patch

from ingestion.entsoe_client import fetch_day_ahead_prices, request_window
from ingestion.ingest import store_raw_response


class EntsoeClientTests(unittest.TestCase):
    @patch("ingestion.entsoe_client.requests.get")
    def test_fetch_uses_utc_window_for_athens_dst_day(self, get):
        response = Mock()
        response.text = "<Publication_MarketDocument/>"
        get.return_value = response

        xml = fetch_day_ahead_prices("test-token", date(2026, 3, 29))

        self.assertEqual(xml, response.text)
        response.raise_for_status.assert_called_once_with()
        self.assertEqual(get.call_args.kwargs["params"]["periodStart"], "202603282200")
        self.assertEqual(get.call_args.kwargs["params"]["periodEnd"], "202603292100")

    @patch("ingestion.entsoe_client.requests.get")
    def test_fetch_uses_configured_bidding_zone(self, get):
        response = Mock()
        response.text = "<Publication_MarketDocument/>"
        get.return_value = response

        with patch.dict(environ, {"ENTSOE_DOMAIN": "configured-zone"}):
            fetch_day_ahead_prices("test-token", date(2026, 9, 27))

        params = get.call_args.kwargs["params"]
        self.assertEqual(params["in_Domain"], "configured-zone")
        self.assertEqual(params["out_Domain"], "configured-zone")

    def test_request_window_is_athens_local_calendar_day(self):
        start, end = request_window(date(2026, 3, 29))

        self.assertEqual(start.isoformat(), "2026-03-29T00:00:00+02:00")
        self.assertEqual(end.isoformat(), "2026-03-30T00:00:00+03:00")


class BronzeStorageTests(unittest.TestCase):
    def test_upserts_raw_xml_with_metadata_and_stable_identity(self):
        collection = Mock()
        target_day = date(2026, 9, 27)
        raw_xml = "<raw>payload</raw>"

        first = store_raw_response(collection, target_day, raw_xml)
        second = store_raw_response(collection, target_day, raw_xml)

        self.assertEqual(first["_id"], second["_id"])
        self.assertEqual(first["requested_date"], "2026-09-27")
        self.assertEqual(first["document_type"], "A44")
        self.assertEqual(first["bidding_zone"], "10YGR-HTSO-----Y")
        self.assertEqual(first["raw_xml"], raw_xml)
        self.assertEqual(first["requested_period"]["timezone"], "Europe/Athens")
        self.assertEqual(collection.replace_one.call_count, 2)
        self.assertTrue(collection.replace_one.call_args.kwargs["upsert"])
        self.assertEqual(collection.replace_one.call_args.args[0], {"_id": first["_id"]})


if __name__ == "__main__":
    unittest.main()
