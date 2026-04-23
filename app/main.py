from __future__ import annotations
import hmac
import os
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.api.health_controller import router as health_router
from app.api.webhook_controller import router as webhook_router
from app.api.signal_controller import router as signal_router
from app.api.analytics_controller import router as analytics_router
from app.api.rate_limiter import limiter

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Telegram Signal Bot API - TradingView Webhook Handler"
)

# Register rate limiter and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Đăng ký các routers
app.include_router(health_router)
app.include_router(webhook_router)
app.include_router(signal_router)
app.include_router(analytics_router)

# Serve static files (dashboard)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_redirect(request: Request):
    """Serve dashboard với optional token auth."""
    if settings.dashboard_token:
        auth_header = request.headers.get("Authorization", "")
        bearer_token = (auth_header.removeprefix("Bearer ").strip() or None) if auth_header.startswith("Bearer ") else None
        if not bearer_token or not hmac.compare_digest(bearer_token, settings.dashboard_token):
            raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
    return RedirectResponse(url="/static/dashboard.html")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=settings.app_port, 
        reload=(settings.app_env == "dev")
    )
