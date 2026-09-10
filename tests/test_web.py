from __future__ import annotations

from aiohttp.test_utils import AioHTTPTestCase

from app.web import create_web_app


class WebAppTests(AioHTTPTestCase):
    async def get_application(self):
        return create_web_app()

    async def test_health_endpoint(self) -> None:
        response = await self.client.get("/health")
        self.assertEqual(response.status, 200)
        self.assertEqual(
            await response.json(),
            {"status": "ok", "service": "rabet-mini-app"},
        )

    async def test_mini_app_contains_brand_and_credits(self) -> None:
        response = await self.client.get("/app")
        body = await response.text()
        self.assertEqual(response.status, 200)
        self.assertIn("no-cache", response.headers["Cache-Control"])
        self.assertIn("RABET", body)
        self.assertIn("Abdulrahman Alzahrani", body)
        self.assertIn("333.alsadi@gmail.com", body)
        self.assertIn("ابدأ التحميل", body)
        self.assertIn("مشروع مستقل", body)
        self.assertNotIn("RABET STUDIO", body)
        self.assertIn("styles.css?v=2.0.1", body)
