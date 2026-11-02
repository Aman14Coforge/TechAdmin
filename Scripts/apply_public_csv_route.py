from __future__ import annotations
import py_compile,shutil
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];APP=ROOT/"StreamlitApp"/"app.py"
def main():
    original=APP.read_text(encoding="utf-8");backup=APP.with_name(f"app.py.before_public_csv_{datetime.now():%Y%m%d_%H%M%S}");shutil.copy2(APP,backup)
    import_line='from infrastructure_public_download import render_public_infrastructure_csv_if_requested  # noqa: E402\n'
    marker='from investigation_report_ui import (\n'
    call='''    if render_public_infrastructure_csv_if_requested():\n        return\n\n''';main_marker='''def main() -> None:\n    init_state()\n\n'''
    try:
        text=original
        if import_line not in text:
            if text.count(marker)!=1:raise RuntimeError("Import marker missing")
            text=text.replace(marker,import_line+marker,1)
        if call not in text:
            if text.count(main_marker)!=1:raise RuntimeError("main marker missing")
            text=text.replace(main_marker,main_marker+call,1)
        APP.write_text(text,encoding="utf-8");py_compile.compile(str(APP),doraise=True)
    except Exception:APP.write_text(original,encoding="utf-8");raise
    print(f"[BACKUP] {backup}");print("[DONE] Signed public CSV route enabled before sign-in")
if __name__=="__main__":main()
