import unittest

import httpx

from App.integration.ivanti.client import IvantiAuthenticationError, IvantiPatchClient
from App.services.patch.config import PatchSettings


class IvantiClientTests(unittest.TestCase):
    def setUp(self):
        self.client = IvantiPatchClient(PatchSettings(
            base_url="https://ivanti.example",
            tenant_id="test-tenant",
            client_id="test-client",
            client_secret="test-secret",
            patch_token_url="https://ivanti.example/connect/token",
        ))
        self.addCleanup(self.client.close)

    def transport(self, handler):
        self.client.http.close()
        self.client.http = httpx.Client(transport=httpx.MockTransport(handler))

    def test_patch_token_is_cached(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 3600})

        self.transport(handler)
        self.assertEqual(self.client.patch_token(), "test-token")
        self.assertEqual(self.client.patch_token(), "test-token")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "POST")

    def test_missing_patch_token_is_rejected(self):
        self.transport(lambda request: httpx.Response(200, json={"expires_in": 3600}))
        with self.assertRaises(IvantiAuthenticationError):
            self.client.patch_token()

    def test_devices_and_patch_queries(self):
        requests = []

        def handler(request):
            requests.append(request)
            path = request.url.path
            if path.endswith("/token"):
                return httpx.Response(200, json={"access_token": "test-token"})
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            if path.endswith("/devices"):
                return httpx.Response(200, json={
                    "value": [{"DiscoveryId": "one"}],
                    "@odata.nextLink": "https://ivanti.example/next?page=2",
                })
            if path == "/next":
                self.assertNotIn("$filter", request.url.params)
                return httpx.Response(200, json={"value": [{"DiscoveryId": "two"}]})
            if path.endswith("/endpoint-vulnerability"):
                rows = [] if "discoveryId" in request.url.params["Filter"] else [{"missingPatches": 1}]
                return httpx.Response(200, json={"data": rows})
            if path.endswith("/deployment-history"):
                return httpx.Response(200, json={"data": [{"patchId": "patch-one"}]})
            if path.endswith("/notification"):
                return httpx.Response(200, json={"data": [{"name": "notification-one"}]})
            self.fail(f"Unexpected endpoint: {path}")

        self.transport(handler)
        self.assertEqual(list(self.client.devices()), [{"DiscoveryId": "one"}, {"DiscoveryId": "two"}])
        self.assertEqual(self.client.vulnerability("one", "device-one"), {"missingPatches": 1})
        self.assertEqual(self.client.deployments("device-one"), [{"patchId": "patch-one"}])
        self.assertEqual(self.client.notification("notification-one"), {"name": "notification-one"})


if __name__ == "__main__":
    unittest.main()