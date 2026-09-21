"""Standalone safe CrowdStrike Windows Security investigation test."""
from __future__ import annotations
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=False)

from App.integration.crowdstrike_failed_login import CrowdStrikeFailedLoginClient

TEST_USERNAME = "Amit.Bhagat"
TEST_EMAIL = "Amit.Bhagat@Coforge.com"
TEST_WINDOW = "1 hour"

client = CrowdStrikeFailedLoginClient()
print("OAuth authentication:", "PASS" if client.authenticate() else "FAIL")
result = client.investigate_failed_login(
    username=TEST_USERNAME,
    email=TEST_EMAIL,
    employee_number=None,
    time_window=TEST_WINDOW,
    correlation_id="manual_crowdstrike_test",
)
print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
