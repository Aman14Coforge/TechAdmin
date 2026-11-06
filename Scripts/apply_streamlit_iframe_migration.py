"""Replace deprecated HTML iframe calls with Streamlit's st.iframe API.

The script scans known TechAdmin Streamlit files and replaces only direct calls:
- st.components.v1.html(...)
- components.html(...)

Streamlit 1.56+ accepts an HTML string in st.iframe. A backup is created for each
changed file, and all changed files are compiled before success is reported.
"""
from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = [
    ROOT / "StreamlitApp" / "app.py",
    ROOT / "StreamlitApp" / "patch_agent_page.py",
    ROOT / "StreamlitApp" / "infrastructure_agent_page.py",
    ROOT / "StreamlitApp" / "compliance_device_browser.py",
]


def main() -> None:
    changed: list[Path] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    originals: dict[Path, str] = {}
    backups: dict[Path, Path] = {}

    try:
        for path in CANDIDATES:
            if not path.exists():
                continue
            original = path.read_text(encoding="utf-8")
            updated = original.replace("st.components.v1.html(", "st.iframe(")
            updated = updated.replace("components.html(", "st.iframe(")
            if updated == original:
                continue
            backup = path.with_name(f"{path.name}.before_st_iframe_{stamp}")
            shutil.copy2(path, backup)
            originals[path] = original
            backups[path] = backup
            path.write_text(updated, encoding="utf-8")
            py_compile.compile(str(path), doraise=True)
            changed.append(path)
    except Exception:
        for path, original in originals.items():
            path.write_text(original, encoding="utf-8")
        raise

    if not changed:
        print("[SKIP] No deprecated components.html calls were found")
        return
    for path in changed:
        print(f"[BACKUP] {backups[path]}")
        print(f"[UPDATED] {path}")
    print("[DONE] Streamlit iframe migration completed")


if __name__ == "__main__":
    main()
