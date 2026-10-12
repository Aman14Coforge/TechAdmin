import unittest
from unittest.mock import patch

from App.services.patch import scheduler


class PatchSchedulerControlTests(unittest.TestCase):
    def test_stop_request_signals_running_scan(self):
        with patch.object(scheduler, "_SCAN_RUNNING", True):
            scheduler._STOP_REQUESTED.clear()
            result = scheduler.request_patch_scan_stop()
            self.assertTrue(result["success"])
            self.assertEqual(result["status"], "STOP_REQUESTED")
            self.assertTrue(scheduler._STOP_REQUESTED.is_set())
            scheduler._STOP_REQUESTED.clear()

    def test_stop_request_without_running_scan_is_safe(self):
        with patch.object(scheduler, "_SCAN_RUNNING", False):
            scheduler._STOP_REQUESTED.clear()
            result = scheduler.request_patch_scan_stop()
            self.assertFalse(result["success"])
            self.assertEqual(result["status"], "NOT_RUNNING")
            self.assertFalse(scheduler._STOP_REQUESTED.is_set())


if __name__ == "__main__":
    unittest.main()
