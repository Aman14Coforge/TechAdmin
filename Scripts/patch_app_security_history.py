"""Apply Security history integration to StreamlitApp/app.py safely."""
from __future__ import annotations
import py_compile
import shutil
from pathlib import Path

APP = Path("StreamlitApp/app.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[SKIP] {label}")
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    print(f"[OK] {label}")
    return text.replace(old, new, 1)


def main() -> None:
    original = APP.read_text(encoding="utf-8")
    backup = APP.with_name("app.py.before_security_history")
    shutil.copy2(APP, backup)
    text = original
    try:
        text = replace_once(
            text,
            "    from App.db.operation_audit import get_user_request_history  # noqa: E402\n",
            "    from App.db.operation_audit import get_user_request_history  # noqa: E402\n"
            "    from App.services.patch.security_history import get_security_query_history  # noqa: E402\n",
            "security history import",
        )
        old = '''def request_history(limit: int = 20) -> list[dict[str, Any]]:\n    user_id = access_info().get("user_id")\n    if user_id:\n        try:\n            return get_user_request_history(user_id, limit=limit)\n        except Exception:\n            return []'''
        new = '''def request_history(limit: int = 20) -> list[dict[str, Any]]:\n    access = access_info()\n    user_id = access.get("user_id")\n    requester_id = user_id or access.get("user_principal_name")\n\n    if requester_id:\n        identity_items: list[dict[str, Any]] = []\n        security_items: list[dict[str, Any]] = []\n\n        if user_id:\n            try:\n                identity_items = get_user_request_history(\n                    user_id,\n                    limit=limit,\n                )\n            except Exception:\n                identity_items = []\n\n        if not PREVIEW_MODE:\n            try:\n                security_items = get_security_query_history(\n                    str(requester_id),\n                    limit=limit,\n                )\n            except Exception:\n                security_items = []\n\n        combined = identity_items + security_items\n        combined.sort(\n            key=lambda item: item.get("requested_at") or datetime.min,\n            reverse=True,\n        )\n        return combined[:limit]'''
        text = replace_once(text, old, new, "combined request history")
        APP.write_text(text, encoding="utf-8")
        py_compile.compile(str(APP), doraise=True)
    except Exception:
        APP.write_text(original, encoding="utf-8")
        raise
    print(f"[DONE] backup: {backup}")


if __name__ == "__main__":
    main()
