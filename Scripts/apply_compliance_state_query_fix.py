"""Update patch_agent_page.py for correct reset and classified chat routing."""
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
        f"patch_agent_page.py.before_state_query_fix_{datetime.now():%Y%m%d_%H%M%S}"
    )
    shutil.copy2(PAGE, backup)

    try:
        text = original

        # Replace any previous compliance browser import with the complete API.
        text = re.sub(
            r"from compliance_device_browser import \([^)]*\)\n",
            "",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r"from compliance_device_browser import [^\n]+\n",
            "",
            text,
        )
        import_block = (
            "from compliance_device_browser import (\n"
            "    category_from_query,\n"
            "    initialize_classified_compliance_state,\n"
            "    open_classified_compliance_view,\n"
            "    render_requested_compliance_devices,\n"
            "    reset_classified_compliance_state,\n"
            "    show_classified_devices_dialog,\n"
            ")\n"
        )
        marker = "from App.integration.iengage.client import IEngageClient\n"
        if text.count(marker) != 1:
            raise RuntimeError("Could not locate Compliance Agent import marker")
        text = text.replace(marker, marker + import_block, 1)

        # Initialize the classified state with the rest of the page state.
        init_marker = "def _init() -> None:\n"
        init_call = "    initialize_classified_compliance_state()\n"
        if init_call not in text:
            text = text.replace(init_marker, init_marker + init_call, 1)

        # Clear classified results when New conversation calls _reset().
        reset_marker = "def _reset() -> None:\n"
        reset_call = "    reset_classified_compliance_state()\n"
        if reset_call not in text:
            text = text.replace(reset_marker, reset_marker + reset_call, 1)

        # Ensure Show devices opens the new dialog.
        text = text.replace(
            '("Show devices", ":material/devices:", _fleet_report_dialog, (operator,))',
            '("Show devices", ":material/devices:", show_classified_devices_dialog, ())',
        )

        # Ensure requested results render once, near other outputs.
        text = re.sub(
            r"\n\s*render_requested_compliance_devices\(\)\n",
            "\n",
            text,
        )
        output_marker = "        if st.session_state.security_patch_search_results:\n"
        render_call = "        render_requested_compliance_devices()\n"
        if text.count(output_marker) != 1:
            raise RuntimeError("Could not locate result-output marker")
        text = text.replace(output_marker, render_call + output_marker, 1)

        # Replace the old device_list chat branch so chat queries use the same
        # classified view as the dialog.
        pattern = re.compile(
            r"    if action == \"device_list\":\n"
            r".*?"
            r"        return\n"
            r"    if action == \"patch_report\":",
            re.DOTALL,
        )
        replacement = '''    if action == "device_list":
        category = category_from_query(
            text,
            metadata.get("device_status"),
        )
        open_classified_compliance_view(
            snapshot=date.fromisoformat(snapshot),
            category=category,
            search=str(metadata.get("device_name") or ""),
        )
        label = {
            "active": "active non-compliant",
            "persistent_14": "persistent 14/14",
            "stale": "stale-reporting",
            "unknown": "last-scan-date-unavailable",
            "resolved": "resolved",
            "all": "all classified",
        }.get(category, "active non-compliant")
        st.session_state.security_conversation.append(
            {
                "role": "assistant",
                "content": (
                    f"Showing {label} devices from the {snapshot} snapshot."
                ),
            }
        )
        _audit_finish(
            query_id,
            status="completed",
            summary={"snapshot": snapshot, "category": category},
        )
        return
    if action == "patch_report":'''
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError("Could not replace the existing device_list chat branch")

        PAGE.write_text(text, encoding="utf-8")
        py_compile.compile(str(PAGE), doraise=True)
    except Exception:
        PAGE.write_text(original, encoding="utf-8")
        raise

    print(f"[BACKUP] {backup}")
    print("[DONE] New conversation reset and classified chat queries fixed")


if __name__ == "__main__":
    main()
