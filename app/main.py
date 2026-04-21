from __future__ import annotations
import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.core.config import settings
from app.api.health_controller import router as health_router
from app.api.webhook_controller import router as webhook_router
from app.api.signal_controller import router as signal_router
from app.api.analytics_controller import router as analytics_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Telegram Signal Bot API - TradingView Webhook Handler"
)

# Đăng ký các routers
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(signal_router)
app.include_router(analytics_router)

# Serve static files (dashboard)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_redirect():
    """Redirect /dashboard to the static HTML dashboard."""
    return RedirectResponse(url="/static/dashboard.html")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=settings.app_port, 
        reload=(settings.app_env == "dev")
    )
