"""Run one compact patch-compliance scan."""
import json
import sys
from App.services.patch.service import PatchService


def main() -> int:
    try:
        result = PatchService().scan()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") == "SUCCEEDED" else 2
    except Exception as exc:
        print(json.dumps({
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
