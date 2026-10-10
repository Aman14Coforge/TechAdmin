import unittest
from datetime import date
from unittest.mock import Mock

from App.services.patch.analytics_service import PatchAnalyticsService
from App.services.patch.semantic import PatchSemanticInterpreter
from StreamlitApp.patch_agent_page import _selected_device_names
import pandas as pd


class PatchAnalyticsTests(unittest.TestCase):
    def test_stale_grid_selection_indices_are_ignored(self):
        frame=pd.DataFrame([{"Device":"DEVICE-A"}])
        self.assertEqual(_selected_device_names(frame,[0,4,-1]),["DEVICE-A"])
        self.assertEqual(_selected_device_names(frame,[4,-1]),[])

    def test_security_queries_route_host_kb_and_all_devices(self):
        interpreter = PatchSemanticInterpreter()
        self.assertEqual(
            interpreter.interpret("Is LP-HYD-0X100314 non-compliant?")["action"],
            "device_report",
        )
        kb = interpreter.interpret("Find devices missing KB5002912")
        self.assertEqual(kb["action"], "patch_search")
        self.assertEqual(kb["patch_query"], "KB5002912")
        self.assertEqual(
            interpreter.interpret("Show all devices for 2026-10-10")["action"],
            "patch_report",
        )

    def test_fleet_report_uses_compact_aggregate_query(self):
        query = Mock()
        query.fleet_report_evidence.return_value = {
            "scope": "all_non_compliant_devices",
            "snapshot": "2026-10-10",
            "summary": {"devices": 16835, "total_missing_instances": 48412},
            "priority_devices": [{"device_name": f"device-{n}"} for n in range(30)],
            "top_missing_patches": [{"patch": "KB1", "affected_devices": 100}],
        }
        ai = Mock()
        ai.analyze.return_value = {"available": True, "analysis": {"executive_summary": "Fleet summary"}}
        service = PatchAnalyticsService()
        service.query = query
        service.ai = ai

        result = service.fleet_report(report_date=date(2026, 10, 10))

        query.fleet_report_evidence.assert_called_once_with(date(2026, 10, 10))
        query.list_devices.assert_not_called()
        query.device_details.assert_not_called()
        self.assertEqual(result["evidence"]["summary"]["devices"], 16835)
        self.assertEqual(len(result["evidence"]["priority_devices"]), 30)
        self.assertTrue(result["ai"]["available"])

    def test_selected_report_only_loads_requested_device_history(self):
        query = Mock()
        query.device_details.return_value = {
            "device_name": "DEVICE-A", "discovery_id": "a", "active": True,
            "days_open": 3, "ticket_status": "NOT_ELIGIBLE", "history": [
                {"scan_date": "2026-10-10", "missing_patch_count": 2, "risk_score": 5,
                 "ip_address": "192.0.2.1", "os_name": "Windows", "patches": [
                     {"KB number": "KB1", "Severity": 2, "Released": "2026-10-01"}
                 ]}
            ],
        }
        ai = Mock()
        ai.analyze.return_value = {"available": True, "analysis": {"executive_summary": "Device summary"}}
        service = PatchAnalyticsService()
        service.query = query
        service.ai = ai

        result = service.fleet_report(
            report_date=date(2026, 10, 10), device_names=["DEVICE-A"]
        )

        query.list_devices.assert_not_called()
        query.device_details.assert_called_once_with("DEVICE-A")
        self.assertEqual(result["evidence"]["summary"]["devices"], 1)
        self.assertEqual(result["evidence"]["devices"][0]["device_name"], "DEVICE-A")
        self.assertTrue(result["ai"]["available"])


if __name__ == "__main__":
    unittest.main()