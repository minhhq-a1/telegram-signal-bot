from __future__ import annotations
import json
import os
import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.api.health_controller import router as health_router
from app.api.webhook_controller import router as webhook_router
from app.api.signal_controller import router as signal_router
from app.api.analytics_controller import router as analytics_router
from app.api.outcome_controller import router as outcome_router
from app.api.config_controller import router as config_router
from app.api.rate_limiter import limiter, rate_limit_exceeded_handler
from app.api.dependencies import require_dashboard_auth

app = FastAPI(title=settings.app_name, version=settings.app_version,
              description="Telegram Signal Bot API - TradingView Webhook Handler")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(signal_router)
app.include_router(analytics_router)
app.include_router(outcome_router)
app.include_router(config_router)

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


@app.get("/dashboard", include_in_schema=False)
async def dashboard(_auth: None = Depends(require_dashboard_auth)) -> HTMLResponse:
    with open(os.path.join(_TEMPLATES_DIR, "dashboard.html"), encoding="utf-8") as f:
        html = f.read()
    token_value = settings.dashboard_token or ""
    # json.dumps encodes quotes and backslashes; replace "</" to prevent
    # premature </script> tag parsing by the browser.
    safe_token = json.dumps(token_value).replace("</", r"<\/")
    injection = f"<script>window.__TOKEN__ = {safe_token};</script>"
    html = html.replace("</head>", f"{injection}\n</head>", 1)
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.app_port,
                reload=(settings.app_env == "dev"))
