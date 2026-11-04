"""Replace direct classification rendering with the Show devices dialog flow."""
from __future__ import annotations

import py_compile
import re
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "StreamlitApp" / "patch_agent_page.py"


def main() -> None:
    original = PAGE.read_text(encoding="utf-8")
    backup = PAGE.with_name(
        f"patch_agent_page.py.before_dialog_browser_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(PAGE, backup)

    try:
        text = original

        # Remove imports from both earlier integration versions.
        text = re.sub(
            r"from compliance_device_browser import \([^)]*\)\n",
            "",
            text,
            flags=re.DOTALL,
        )
        text = text.replace(
            "from compliance_device_browser import render_compliance_device_browser\n",
            "",
        )
        new_import = (
            "from compliance_device_browser import (\n"
            "    render_requested_compliance_devices,\n"
            "    show_classified_devices_dialog,\n"
            ")\n"
        )
        marker = "from App.integration.iengage.client import IEngageClient\n"
        if new_import not in text:
            if text.count(marker) != 1:
                raise RuntimeError("Could not locate Compliance Agent import marker")
            text = text.replace(marker, marker + new_import, 1)

        # Remove the earlier unconditional/conditional browser call.
        text = re.sub(
            r"\n\s*if not st\.session_state\.security_conversation and not st\.session_state\.security_job:\n"
            r"\s*render_compliance_device_browser\(_latest_snapshot\(\)\)\n",
            "\n",
            text,
        )
        text = re.sub(
            r"\n\s*render_compliance_device_browser\(_latest_snapshot\(\)\)\n",
            "\n",
            text,
        )

        # Existing quick action uses _fleet_report_dialog. Point only Show devices
        # to the new dialog while preserving every other action.
        old_action = '("Show devices", ":material/devices:", _fleet_report_dialog, (operator,))'
        new_action = '("Show devices", ":material/devices:", show_classified_devices_dialog, ())'
        if old_action in text:
            text = text.replace(old_action, new_action, 1)
        elif new_action not in text:
            raise RuntimeError("Could not locate the Show devices quick action")

        # Render results in the same place as the old list/report outputs, but only
        # after the dialog has submitted a request.
        render_call = "        render_requested_compliance_devices()\n"
        output_marker = "        if st.session_state.security_patch_search_results:\n"
        if render_call not in text:
            if text.count(output_marker) != 1:
                raise RuntimeError("Could not locate Compliance Agent output marker")
            text = text.replace(output_marker, render_call + output_marker, 1)

        PAGE.write_text(text, encoding="utf-8")
        py_compile.compile(str(PAGE), doraise=True)
    except Exception:
        PAGE.write_text(original, encoding="utf-8")
        raise

    print(f"[BACKUP] {backup}")
    print("[DONE] Show devices now opens the classified snapshot dialog")


if __name__ == "__main__":
    main()
