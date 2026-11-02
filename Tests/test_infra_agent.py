import asyncio
import os
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.infra_ticket_service import InfraTicketService, infra_config_from_env
from App.integration.iengage.models import InfraTicketDevice, InfraTicketInput
from App.integration.itom.client import (
    SITE_ALERTS_SQL,
    SITE_SCORES_SQL,
    ItomReadOnlyClient,
    assert_read_only_sql,
    format_interval,
    load_query,
    normalize_row,
)
from App.integration.itom.config import ItomConfig
from App.services.infra.service import InfrastructureService
from App.services.infra.ticket_service import InfrastructureTicketService


def mock_client():
    with patch.dict(os.environ, {"ITOM_USE_MOCK_DATA": "true"}, clear=True), patch(
        "App.integration.itom.config.load_dotenv"
    ):
        return ItomReadOnlyClient(ItomConfig.from_env())


def iengage_config(**changes):
    with patch.dict(os.environ, {}, clear=True), patch("App.integration.iengage.config.load_dotenv"):
        base = IEngageConfig.from_env()
    return replace(
        base, enabled=True, dry_run=True, url="https://tickets.example.test/create",
        requester_code="12345", emp_code="12345", requester_mobile="1234567890",
        request_type="Incident", category_id="1", subcategory_id="2", priority_id="3", location_id="4",
        **changes,
    )


def ticket_input(device_count=3, **changes):
    values = dict(
        location_name="Pune",
        site_status="warning",
        site_score=85.3,
        priority="P2",
        site_reason="Down or Critical nodes need attention",
        devices=[InfraTicketDevice(f"PUN-SW-{i:02d}", "Down", "SOLARWINDS") for i in range(1, device_count + 1)],
        triggered_by="ops@example.test",
    )
    values.update(changes)
    return InfraTicketInput(**values)


class ReadOnlySqlTests(unittest.TestCase):
    def test_bundled_queries_are_read_only(self):
        for name in (SITE_SCORES_SQL, SITE_ALERTS_SQL):
            self.assertTrue(load_query(name).lstrip().startswith(("--", "WITH")))

    def test_rejects_writes_and_multiple_statements(self):
        for sql in (
            "DELETE FROM public.sync_runs",
            "WITH x AS (SELECT 1) UPDATE public.sync_runs SET status = 'X'",
            "SELECT 1; DROP TABLE public.sync_runs",
        ):
            with self.assertRaises(ValueError):
                assert_read_only_sql(sql)

    def test_requires_password_for_live_database(self):
        with patch.dict(os.environ, {}, clear=True), patch("App.integration.itom.config.load_dotenv"):
            config = ItomConfig.from_env()
        self.assertEqual(config.user, "itom_ro")
        with self.assertRaisesRegex(ValueError, "ITOM_DB_PASSWORD"):
            config.validate()

    def test_normalizes_numeric_and_interval_values(self):
        row = normalize_row({"site_score": Decimal("85.3"), "data_age": timedelta(days=1, hours=2, minutes=5)})
        self.assertEqual(row, {"site_score": 85.3, "data_age": "1d 2h 5m"})
        self.assertEqual(format_interval(timedelta(minutes=7)), "7m")


class InfrastructureServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = InfrastructureService(mock_client())
        self.sites = self.service.site_scores()
        self.alerts = self.service.site_alerts()

    def test_summary_counts_locations_by_status(self):
        summary = self.service.summarize(self.sites)
        self.assertEqual(summary["total_locations"], 28)
        self.assertEqual(summary["by_status"], {"critical": 10, "warning": 14, "healthy": 4})

    def test_sites_and_devices_for_a_status(self):
        critical = self.service.sites_with_status(self.sites, "Critical")
        self.assertTrue(all(site["site_status"] == "critical" for site in critical))
        devices = self.service.devices_for_site(self.alerts, "Brazil")
        self.assertTrue(devices)
        self.assertTrue(all(row["priority"] == "P1" for row in devices))
        self.assertEqual(self.service.devices_for_site(self.alerts, "Dubai"), [])


class InfraTicketTests(unittest.TestCase):
    def test_description_lists_every_selected_device(self):
        service = InfraTicketService(config=iengage_config())
        text = service._build_description(ticket_input())
        self.assertIn("Site: Pune (P2, warning, combined score 85.3).", text)
        for name in ("PUN-SW-01", "PUN-SW-02", "PUN-SW-03"):
            self.assertIn(name, text)
        self.assertIn("Raised by: ops@example.test.", text)

    def test_long_device_lists_are_truncated_within_the_limit(self):
        service = InfraTicketService(config=iengage_config())
        text = service._build_description(ticket_input(device_count=120))
        self.assertLessEqual(len(text), service.config.description_max_length)
        self.assertIn("more (full list in TechAdmin)", text)
        self.assertIn("Raised by:", text)

    def test_payload_uses_first_device_and_priority_override(self):
        service = InfraTicketService(config=iengage_config())
        with patch.dict(os.environ, {"INFRA_IENGAGE_P1_PRIORITY_ID": "9"}):
            details = service.build_service_details(ticket_input(priority="P1"))
        self.assertEqual(details["RequesterAssetCode"], "PUN-SW-01")
        self.assertEqual(details["RequestPriorityId"], "9")

    def test_category_overrides(self):
        with patch.dict(os.environ, {"INFRA_IENGAGE_CATEGORY_ID": "77"}):
            config = infra_config_from_env(iengage_config())
        self.assertEqual(config.category_id, "77")
        self.assertEqual(config.subcategory_id, "2")

    def test_requires_a_device(self):
        service = InfraTicketService(config=iengage_config())
        with self.assertRaises(ValueError):
            asyncio.run(service.create_infra_ticket(ticket_input(devices=[])))

    def test_dry_run_ticket_through_service(self):
        tickets = InfrastructureTicketService(InfraTicketService(config=iengage_config()))
        site = {"location_name": "Brazil", "site_status": "critical", "site_score": 62.3}
        devices = [{"device_name": "BRA-SW-01", "device_status": "Down", "source_system": "SOLARWINDS"}]
        item = tickets.build_input(site, devices, requested_by="ops")
        self.assertEqual(item.priority, "P1")
        result = tickets.raise_ticket(item)
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(result["device_names"], ["BRA-SW-01"])


if __name__ == "__main__":
    unittest.main()
