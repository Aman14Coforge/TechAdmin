from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

SCRIPT = Path(__file__).resolve()
ROOT = next((parent for parent in SCRIPT.parents if (parent / ".env").is_file()), None)
if ROOT is None:
    raise FileNotFoundError("Could not locate .env.")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)

from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import PatchTicketInput
from App.integration.iengage.ticket_service import PatchTicketService


async def main() -> None:
    config = IEngageConfig.from_env()
    print(json.dumps({"enabled": config.enabled, "dry_run": config.dry_run, "url": config.url}, indent=2))
    result = await PatchTicketService(config).create_patch_ticket(PatchTicketInput(
        device_name="TEST-DEVICE-DO-NOT-ACTION",
        missing_patch_count=2,
        missing_patch_names=["TEST Security Update", "TEST Cumulative Update"],
        consecutive_non_compliant_days=14,
        discovery_id="TEST-DISCOVERY-ID",
        device_id="TEST-DEVICE-ID",
        operating_system="Microsoft Windows 11 Enterprise Edition, 64-bit",
        triggered_by="TechAdmin integration test",
        trigger_type="manual-test",
        additional_description="Integration validation test.",
    ))
    print(json.dumps(result.__dict__, indent=2, ensure_ascii=False, default=str))
    if not result.success:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
