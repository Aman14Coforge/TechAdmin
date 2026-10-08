"""Safely and idempotently integrate patch_report_ui into StreamlitApp/app.py."""
from __future__ import annotations
import py_compile, shutil
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent
APP=ROOT/"StreamlitApp"/"app.py"
BACKUP=ROOT/"StreamlitApp"/("app.py.before_patch_report_ui_"+datetime.now().strftime("%Y%m%d_%H%M%S"))

def apply(text: str, old: str, new: str, label: str) -> str:
    if new in text: print(f"[SKIP] {label}"); return text
    if text.count(old)!=1: raise RuntimeError(f"{label}: expected one exact match, found {text.count(old)}")
    print(f"[OK] {label}"); return text.replace(old,new,1)

def main() -> None:
    if not APP.exists(): raise FileNotFoundError(APP)
    original=APP.read_text(encoding="utf-8"); shutil.copy2(APP,BACKUP); text=original
    try:
        text=apply(text,
            "from investigation_report_ui import render_investigation_report\n",
            "from investigation_report_ui import render_investigation_report\nfrom patch_report_ui import initialize_patch_report_state, render_patch_report\n",
            "import")
        text=apply(text,
            '    st.session_state.setdefault("ollama_check_result", None)\n',
            '    st.session_state.setdefault("ollama_check_result", None)\n    initialize_patch_report_state()\n',
            "state")
        marker='def render_result(intent: str, result: Dict[str, Any]) -> None:\n'
        text=apply(text, marker, marker+'    if intent == "patch_report":\n        render_patch_report(result)\n        return\n', "renderer")
        old='    target = metadata.get("email") or metadata.get("username") or metadata.get("user_id") or "Unknown target"\n'
        new='    if intent in {"patch_report", "patch_scan"}:\n        target = metadata.get("device_name") or "Ivanti patch fleet"\n    elif intent == "patch_ticket":\n        target = metadata.get("device_name") or "Patch remediation"\n    else:\n        target = metadata.get("email") or metadata.get("username") or metadata.get("user_id") or "Unknown target"\n'
        text=apply(text,old,new,"operation target")
        old_recent='            "Target": metadata.get("email") or metadata.get("username") or "Unknown target",\n'
        new_recent='            "Target": (metadata.get("device_name") or ("Ivanti patch fleet" if response.get("intent") in {"patch_report", "patch_scan"} else None) or metadata.get("email") or metadata.get("username") or "Unknown target"),\n'
        text=apply(text,old_recent,new_recent,"recent target")
        APP.write_text(text,encoding="utf-8")
        py_compile.compile(str(APP),doraise=True)
        py_compile.compile(str(ROOT/"StreamlitApp"/"patch_report_ui.py"),doraise=True)
    except Exception:
        APP.write_text(original,encoding="utf-8")
        print("[RESTORED] app.py because validation failed")
        raise
    print(f"[BACKUP] {BACKUP}"); print("[DONE] app.py compiled successfully")
if __name__=="__main__": main()
