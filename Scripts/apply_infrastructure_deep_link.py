from __future__ import annotations
import py_compile,shutil
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; APP=ROOT/"StreamlitApp"/"app.py"
def main():
    original=APP.read_text(encoding="utf-8"); backup=APP.with_name(f"app.py.before_infra_link_{datetime.now():%Y%m%d_%H%M%S}"); shutil.copy2(APP,backup)
    addition='''    requested_page = str(st.query_params.get("page", "")).strip().casefold()\n    requested_site = str(st.query_params.get("infrastructure_site", "")).strip()\n    if requested_page == "infrastructure" or requested_site:\n        st.session_state.page = "infrastructure"\n\n'''; marker='''    history = request_history()\n\n'''
    if addition in original: print("[SKIP] Already configured"); return
    if original.count(marker)!=1: raise RuntimeError("Could not locate request_history marker")
    try: APP.write_text(original.replace(marker,marker+addition,1),encoding="utf-8"); py_compile.compile(str(APP),doraise=True)
    except Exception: APP.write_text(original,encoding="utf-8"); raise
    print(f"[BACKUP] {backup}"); print("[DONE] Deep link enabled")
if __name__=="__main__": main()
