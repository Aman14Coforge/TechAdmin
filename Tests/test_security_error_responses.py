import asyncio
import json
import unittest
from unittest.mock import Mock

from starlette.requests import Request

from App.integration.ivanti.client import IvantiPatchClient
from App.main import handle_unexpected_api_exception


class SecurityErrorResponseTests(unittest.TestCase):
    def test_ivanti_preflight_does_not_return_exception_details(self):
        client = object.__new__(IvantiPatchClient)
        client._get_json = Mock(side_effect=RuntimeError("private endpoint and credential detail"))

        result = client.preflight()

        serialized = json.dumps(result)
        self.assertNotIn("private endpoint", serialized)
        self.assertNotIn("credential detail", serialized)
        self.assertEqual(
            result["checks"]["people"]["error"],
            "Request failed. See server logs for details.",
        )

    def test_global_api_error_response_hides_exception_details(self):
        request = Request({
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [],
            "server": ("localhost", 443),
            "client": ("127.0.0.1", 50000),
        })

        response = asyncio.run(
            handle_unexpected_api_exception(
                request,
                RuntimeError("private database connection string"),
            )
        )
        body = json.loads(response.body)

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private database connection string", response.body.decode())
        self.assertEqual(body["detail"], "An unexpected error occurred.")
        self.assertTrue(body["reference_id"])


if __name__ == "__main__":
    unittest.main()
