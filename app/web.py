from __future__ import annotations

from pathlib import Path

from aiohttp import web


STATIC_DIR = Path(__file__).with_name("webapp")


async def index(_: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "rabet-mini-app"})


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/app", index)
    app.router.add_get("/health", health)
    app.router.add_static("/static", STATIC_DIR, show_index=False)
    return app
