import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx

from App.integration.iengage.client import IEngageClient
from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import PatchTicketInput
from App.integration.iengage.ticket_service import PatchTicketService


def make_config():
    with patch.dict(os.environ, {}, clear=True), patch(
        "App.integration.iengage.config.load_dotenv"
    ):
        base = IEngageConfig.from_env()
    return replace(
        base, enabled=True, dry_run=False, url="https://tickets.example.test/create",
        ecserp="test-erp", auth_key="test-secret", requester_code="12345",
        emp_code="12345", requester_mobile="1234567890", request_type="Incident",
        category_id="1", subcategory_id="2", priority_id="3", location_id="4",
    )


class ConfigTests(unittest.TestCase):
    def test_loads_root_file_without_overriding_process_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "IENGAGE_ENABLED=true\nIENGAGE_DRY_RUN=true\n"
                "IENGAGE_URL=https://tickets.example.test/create\n", encoding="utf-8"
            )
            with patch.dict(os.environ, {"IENGAGE_DRY_RUN": "false", "IENGAGE_ENABLED": "false"}, clear=True), patch(
                "App.integration.iengage.config.ENV_FILE", env_file
            ):
                config = IEngageConfig.from_env()
                self.assertEqual(config.url, "https://tickets.example.test/create")
                self.assertFalse(config.dry_run)
                self.assertFalse(config.enabled)

    def test_enabled_without_url_fails(self):
        with patch.dict(os.environ, {"IENGAGE_ENABLED": "true"}, clear=True), patch(
            "App.integration.iengage.config.load_dotenv"
        ):
            with self.assertRaisesRegex(ValueError, "IENGAGE_URL is missing"):
                IEngageConfig.from_env()

    def test_live_config_requires_credentials(self):
        with self.assertRaisesRegex(ValueError, "IENGAGE_AUTH_KEY"):
            replace(make_config(), auth_key="").validate()


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def submit(self, payload, status=200):
        config = make_config()
        config.validate()
        captured = []

        def handler(request):
            captured.append(request)
            return httpx.Response(status, json=payload)

        transport = httpx.MockTransport(handler)
        factory = httpx.AsyncClient

        def mocked_client(**kwargs):
            return factory(transport=transport, **kwargs)

        with patch("App.integration.iengage.client.httpx.AsyncClient", side_effect=mocked_client):
            result = await PatchTicketService(config).create_patch_ticket(
                PatchTicketInput(device_name="TEST-DEVICE", missing_patch_count=2)
            )
        return result, captured

    async def test_multipart_creation_and_redaction(self):
        result, captured = await self.submit({"success": True, "RequestID": "INC000107723"})
        self.assertTrue(result.success)
        self.assertTrue(result.sent)
        self.assertEqual(result.ticket_id, "INC000107723")
        body = captured[0].content.decode()
        self.assertIn('name="ECSerp"', body)
        self.assertIn('name="AuthKey"', body)
        self.assertIn('name="serviceDetails"', body)
        self.assertIn('"isSave": true', body)
        self.assertIn('"RequesterAssetCode": "TEST-DEVICE"', body)
        self.assertNotIn("test-secret", json.dumps(result.request_preview))

    async def test_success_message_without_reference_is_not_a_ticket_id(self):
        result, _ = await self.submit({"message": "Request created successfully"})
        self.assertTrue(result.success)
        self.assertIsNone(result.ticket_id)
        self.assertIn("Request created successfully", result.message)

    async def test_extract_id_from_success_message(self):
        result, _ = await self.submit({"message": "Ticket was created. ID: INC000107723"})
        self.assertTrue(result.success)
        self.assertEqual(result.ticket_id, "INC000107723")

    async def test_extract_id_from_html_message(self):
        result, _ = await self.submit({"message": "Ticket created: <b>INC000107724</b>"})
        self.assertTrue(result.success)
        self.assertEqual(result.ticket_id, "INC000107724")

    async def test_extract_id_from_wrapped_data_id(self):
        result, _ = await self.submit({"success": True, "data": {"id": "INC000107725"}})
        self.assertTrue(result.success)
        self.assertEqual(result.ticket_id, "INC000107725")

    async def test_extract_id_embedded_in_iengage_success_message(self):
        result, _ = await self.submit({"StatusCode": 200, "Message": "107729_INC000107729"})
        self.assertTrue(result.success)
        self.assertEqual(result.ticket_id, "INC000107729")

    async def test_does_not_treat_date_as_ticket_id(self):
        result, _ = await self.submit({"message": "Request created successfully on 2026-10-11"})
        self.assertTrue(result.success)
        self.assertIsNone(result.ticket_id)

    async def test_failure_takes_precedence_over_reference(self):
        result, _ = await self.submit({"success": False, "RequestID": "INC000107723", "message": "Rejected"})
        self.assertFalse(result.success)
        self.assertIsNone(result.ticket_id)

    async def test_http_failure(self):
        result, _ = await self.submit({"message": "Unauthorized"}, status=401)
        self.assertFalse(result.success)
        self.assertEqual(result.status_code, 401)

    async def test_dry_run_never_sends(self):
        with patch("App.integration.iengage.client.httpx.AsyncClient") as client:
            result = await PatchTicketService(replace(make_config(), dry_run=True)).create_patch_ticket(
                PatchTicketInput(device_name="TEST-DEVICE", missing_patch_count=1)
            )
        client.assert_not_called()
        self.assertTrue(result.dry_run)
        self.assertFalse(result.sent)

    async def test_read_timeout_warns_against_duplicate_submission(self):
        factory = httpx.AsyncClient

        def handler(request):
            raise httpx.ReadTimeout("Response not received", request=request)

        with patch(
            "App.integration.iengage.client.httpx.AsyncClient",
            side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
        ):
            result = await PatchTicketService(make_config()).create_patch_ticket(
                PatchTicketInput(device_name="TEST-DEVICE", missing_patch_count=1)
            )
        self.assertFalse(result.success)
        self.assertTrue(result.sent)
        self.assertIn("before retrying", result.message)


if __name__ == "__main__":
    unittest.main()