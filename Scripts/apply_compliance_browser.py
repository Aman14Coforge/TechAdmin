"""Safely add the enhanced compliance browser to current patch_agent_page.py."""
from __future__ import annotations
import py_compile
import shutil
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "StreamlitApp" / "patch_agent_page.py"
def main() -> None:
    original = PAGE.read_text(encoding="utf-8")
    backup = PAGE.with_name(f"patch_agent_page.py.before_classification_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(PAGE, backup)
    import_line = "from compliance_device_browser import render_compliance_device_browser\n"
    import_marker = "from App.integration.iengage.client import IEngageClient\n"
    call = '''        if not st.session_state.security_conversation and not st.session_state.security_job:\n            render_compliance_device_browser(_latest_snapshot())\n\n'''
    call_marker = '''        for turn in st.session_state.security_conversation:\n'''
    try:
        text = original
        if import_line not in text:
            if text.count(import_marker) != 1:
                raise RuntimeError("Could not locate iEngage import marker")
            text = text.replace(import_marker, import_marker + import_line, 1)
        if call not in text:
            if text.count(call_marker) != 1:
                raise RuntimeError("Could not locate conversation marker")
            text = text.replace(call_marker, call + call_marker, 1)
        PAGE.write_text(text, encoding="utf-8")
        py_compile.compile(str(PAGE), doraise=True)
    except Exception:
        PAGE.write_text(original, encoding="utf-8")
        raise
    print(f"[BACKUP] {backup}")
    print("[DONE] Enhanced compliance browser added")
if __name__ == "__main__":
    main()
