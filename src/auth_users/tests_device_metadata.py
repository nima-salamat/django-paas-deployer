from types import SimpleNamespace

from django.test import TestCase

from .device_metadata import device_descriptor, parse_user_agent
from .models import Device
from users.models import User


class DeviceMetadataTests(TestCase):
    def test_parse_chrome_windows_user_agent(self):
        parsed = parse_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        )
        self.assertEqual(parsed["browser"], "Chrome")
        self.assertEqual(parsed["browser_version"], "151.0.0.0")
        self.assertEqual(parsed["os"], "Windows")
        self.assertEqual(parsed["os_version"], "Windows 10/11")
        self.assertEqual(parsed["device_type"], "desktop")

    def test_parse_android_model_and_mobile_type(self):
        parsed = parse_user_agent(
            "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP2A.240805.005) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Mobile Safari/537.36"
        )
        self.assertEqual(parsed["browser"], "Chrome")
        self.assertEqual(parsed["os"], "Android")
        self.assertEqual(parsed["os_version"], "14")
        self.assertEqual(parsed["device_type"], "mobile")
        self.assertEqual(parsed["device_model"], "Pixel 8")

    def test_device_descriptor_uses_session_snapshot_over_device_metadata(self):
        user = User.objects.create_user(username="metadata-user", password="pass12345")
        device = Device.objects.create(
            user=user,
            name="",
            client="Web browser",
            platform="Windows",
            user_agent="",
            metadata={
                "browser": "Chrome",
                "browser_version": "151",
                "os": "Windows",
                "os_version": "Windows 10/11",
                "client_signature": "device-signature",
            },
        )
        session = SimpleNamespace(
            metadata={
                "browser": "Firefox",
                "browser_version": "145",
                "os": "Linux",
                "os_version": "",
                "device_type": "desktop",
                "client_metadata": {"timezone": "Asia/Baku", "locale": "en-US"},
            },
            user_agent="Mozilla/5.0 X11 Linux x86_64 Firefox/145.0",
            last_ip="203.0.113.42",
        )
        descriptor = device_descriptor(device, session=session)

        self.assertEqual(descriptor["browser"], "Firefox")
        self.assertEqual(descriptor["browser_version"], "145")
        self.assertEqual(descriptor["os"], "Linux")
        self.assertEqual(descriptor["ip"], "203.0.113.42")
        self.assertEqual(descriptor["client_signature"], "device-signature")
        self.assertEqual(descriptor["client_metadata"]["timezone"], "Asia/Baku")

    def test_issue_tokens_persist_structured_client_and_server_metadata(self):
        user = User.objects.create_user(username="login-metadata", password="pass12345")
        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "198.51.100.10",
                "HTTP_USER_AGENT": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36"
                ),
            },
            data={
                "device_id": "11111111-1111-4111-8111-111111111111",
                "client": "Web browser",
                "platform": "Windows",
                "client_signature": "abc123",
                "client_metadata": {
                    "locale": "en-US",
                    "timezone": "Asia/Baku",
                    "screen_width": 1920,
                    "screen_height": 1080,
                    "hardware_concurrency": 16,
                },
            },
        )
        from .services import issue_tokens_for_user

        tokens = issue_tokens_for_user(user, request=request, device_id=request.data["device_id"])
        device = Device.objects.get(public_id=request.data["device_id"])
        session = user.auth_sessions.get(session_id=tokens["session_id"])

        self.assertEqual(device.last_ip, "198.51.100.10")
        self.assertEqual(device.metadata["browser"], "Chrome")
        self.assertEqual(device.metadata["os"], "Windows")
        self.assertEqual(device.metadata["client_signature"], "abc123")
        self.assertEqual(device.metadata["client_metadata"]["hardware_concurrency"], 16)
        self.assertEqual(session.last_ip, "198.51.100.10")
        self.assertEqual(session.metadata["browser_version"], "151.0.0.0")



    def test_session_api_exposes_rich_device_descriptor(self):
        from rest_framework.test import APIClient
        from .services import issue_tokens_for_user

        user = User.objects.create_user(username="session-api-meta", password="pass12345")
        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "203.0.113.7",
                "HTTP_USER_AGENT": "Mozilla/5.0 X11 Linux x86_64 Firefox/145.0",
            },
            data={
                "device_id": "22222222-2222-4222-8222-222222222222",
                "client_metadata": {"timezone": "Asia/Baku", "locale": "en-US"},
                "client_signature": "session-api-signature",
            },
        )
        tokens = issue_tokens_for_user(user, request=request, device_id=request.data["device_id"])

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = client.get("/auth/api/sessions/")

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]["device"]
        self.assertEqual(result["browser"], "Firefox")
        self.assertEqual(result["os"], "Linux")
        self.assertEqual(result["ip"], "203.0.113.7")
        self.assertEqual(result["client_signature"], "session-api-signature")
        self.assertEqual(result["client_metadata"]["timezone"], "Asia/Baku")
