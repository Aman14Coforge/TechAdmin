"""Safe Ivanti API readiness check."""
import json
from App.integration.ivanti.client import IvantiPatchClient


def main() -> None:
    client = IvantiPatchClient()
    try:
        print(json.dumps({
            "auth_diagnostic": client.inventory_auth_diagnostic(),
            "preflight": client.preflight(),
        }, indent=2, default=str))
    finally:
        client.close()


if __name__ == "__main__":
    main()
