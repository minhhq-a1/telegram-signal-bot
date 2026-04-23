# Rate Limiting Webhook Endpoint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-IP rate limiting (50 requests/minute) to the TradingView webhook endpoint with HTTP 429 response and environment variable configuration.

**Architecture:** Use `slowapi` library for FastAPI rate limiting. Initialize a limiter instance in a dedicated module, apply the decorator to the webhook handler, configure via environment variable in Settings, and register an exception handler in the FastAPI app.

**Tech Stack:** Python 3.12, FastAPI 0.115, slowapi>=0.1.9, Pydantic v2, pydantic-settings

---

## File Structure

**New files:**
- `app/api/rate_limiter.py` — Limiter instance initialization

**Modified files:**
- `requirements.txt` — Add slowapi dependency
- `app/core/config.py` — Add webhook_rate_limit setting
- `app/api/webhook_controller.py` — Apply @limiter.limit decorator
- `app/main.py` — Register exception handler
- `.env.example` — Document WEBHOOK_RATE_LIMIT
- `tests/integration/test_webhook_rate_limiting.py` — New integration tests

---

## Task T1: Add slowapi dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add slowapi to requirements.txt**

Open `requirements.txt` and add the line:
```
slowapi>=0.1.9
```

Exact location: add after line with `httpx==0.27.2` (before `python-dotenv==1.0.1`)

Updated `requirements.txt` should have:
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy==2.0.35
psycopg[binary]>=3.2.4
pydantic==2.9.2
pydantic-settings==2.5.2
httpx==0.27.2
slowapi>=0.1.9
python-dotenv==1.0.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Install slowapi in venv**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m pip install "slowapi>=0.1.9"
```

Expected: Installation succeeds, shows "Successfully installed slowapi-X.Y.Z"

- [ ] **Step 3: Verify installation**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -c "import slowapi; print(f'slowapi {slowapi.__version__} installed')"
```

Expected: Output shows version number (e.g., "slowapi 0.1.9 installed")

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add slowapi>=0.1.9 for rate limiting"
```

---

## Task T2: Create rate limiter module

**Files:**
- Create: `app/api/rate_limiter.py`

- [ ] **Step 1: Create rate_limiter.py**

Create file `/Users/minhhq/Documents/telegram-signal-bot/app/api/rate_limiter.py` with:

```python
"""Rate limiter initialization for FastAPI endpoints."""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

- [ ] **Step 2: Verify file exists and has correct content**

Run:
```bash
cat /Users/minhhq/Documents/telegram-signal-bot/app/api/rate_limiter.py
```

Expected: Output shows the exact code above (3 lines of imports + limiter initialization)

- [ ] **Step 3: Commit**

```bash
git add app/api/rate_limiter.py
git commit -m "feat: create rate limiter module with per-IP tracking"
```

---

## Task T3: Add webhook_rate_limit configuration

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Read current config.py**

Read the file to understand current Settings structure.

- [ ] **Step 2: Add webhook_rate_limit field**

In `app/core/config.py`, after line 24 (`dashboard_token: str | None = None`), add:

```python
    # Webhook Rate Limiting
    webhook_rate_limit: int = 50
```

Complete file should look like:
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # App Config
    app_name: str = "Telegram Signal Bot"
    app_version: str = "1.0.0"
    app_env: str = "dev"
    app_port: int = 8080  # Railway overrides via PORT env var in start.sh
    log_level: str = "INFO"

    # Security
    tradingview_shared_secret: str

    # Database
    database_url: str

    # Telegram API
    telegram_bot_token: str
    telegram_main_chat_id: str
    telegram_warn_chat_id: str
    telegram_admin_chat_id: str

    # Dashboard
    dashboard_token: str | None = None

    # Webhook Rate Limiting
    webhook_rate_limit: int = 50

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

settings = Settings()
```

- [ ] **Step 3: Verify syntax**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -c "from app.core.config import settings; print(f'webhook_rate_limit={settings.webhook_rate_limit}')"
```

Expected: Output shows `webhook_rate_limit=50` (from .env or default)

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py
git commit -m "config: add webhook_rate_limit setting (default 50, reads env var)"
```

---

## Task T4: Apply rate limiter decorator to webhook

**Files:**
- Modify: `app/api/webhook_controller.py`

- [ ] **Step 1: Add import at top of file**

After existing imports (after line 15), add:

```python
from app.core.config import settings
from app.api.rate_limiter import limiter
```

File should have imports:
```python
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.domain.schemas import WebhookAcceptedResponse, ErrorResponse
from app.repositories.webhook_event_repo import WebhookEventRepository
from app.repositories.signal_repo import SignalRepository
from app.repositories.filter_result_repo import FilterResultRepository
from app.repositories.decision_repo import DecisionRepository
from app.repositories.telegram_repo import TelegramRepository
from app.repositories.config_repo import ConfigRepository
from app.repositories.market_event_repo import MarketEventRepository
from app.services.telegram_notifier import TelegramNotifier
from app.services.webhook_ingestion_service import WebhookIngestionService
from app.api.rate_limiter import limiter
```

- [ ] **Step 2: Add decorator to webhook handler**

Find the `@router.post("/api/v1/webhooks/tradingview", ...)` decorator (line 19-27).

Add the rate limiter decorator **between** the router decorator and the function definition:

```python
@router.post(
    "/api/v1/webhooks/tradingview",
    responses={
        200: {"model": WebhookAcceptedResponse, "description": "Signal accepted and processed"},
        400: {"model": ErrorResponse, "description": "Invalid JSON, schema validation error, or invalid secret"},
        409: {"model": ErrorResponse, "description": "Duplicate signal (already processed)"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit(f"{settings.webhook_rate_limit}/minute")
async def handle_tradingview_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
```

**Important:** The `@limiter.limit()` must be placed AFTER `@router.post()` and BEFORE the `async def` function definition.

- [ ] **Step 3: Verify file syntax**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m py_compile app/api/webhook_controller.py
```

Expected: No errors (file compiles successfully)

- [ ] **Step 4: Commit**

```bash
git add app/api/webhook_controller.py
git commit -m "feat: apply rate limiting decorator to webhook endpoint (50/min per IP)"
```

---

## Task T5: Register exception handler in FastAPI app

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add imports**

After existing imports, add (after line with `from app.api` imports):

```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.rate_limiter import limiter
```

- [ ] **Step 2: Register limiter with app state**

Find the line `app = FastAPI(...)` (around line 10-20).

After the app initialization, add these two lines:

```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

Example of how it should look:
```python
app = FastAPI(...)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ... rest of app setup
```

- [ ] **Step 3: Verify syntax**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m py_compile app/main.py
```

Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: register rate limit exception handler in FastAPI app"
```

---

## Task T6: Document rate limiting in .env.example

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Read current .env.example**

Check current contents.

- [ ] **Step 2: Add rate limit configuration documentation**

Append to `.env.example` (at the end, before EOF):

```
# Rate Limiting
# Max requests per minute to webhook endpoint per IP address
WEBHOOK_RATE_LIMIT=50
```

- [ ] **Step 3: Verify content**

Run:
```bash
tail -5 /Users/minhhq/Documents/telegram-signal-bot/.env.example
```

Expected: Last lines show the rate limiting configuration

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "docs: add WEBHOOK_RATE_LIMIT to .env.example"
```

---

## Task T7: Write integration tests for rate limiting

**Files:**
- Create: `tests/integration/test_webhook_rate_limiting.py`

- [ ] **Step 1: Create test file**

Create `/Users/minhhq/Documents/telegram-signal-bot/tests/integration/test_webhook_rate_limiting.py` with:

```python
"""Integration tests for webhook rate limiting."""
from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings


def test_webhook_rate_limit_with_overrides(client: TestClient, monkeypatch):
    """Test rate limiting allows requests up to limit, then blocks with 429."""
    # Override to use low limit (5/minute) for quick testing
    monkeypatch.setattr(settings, "webhook_rate_limit", 5)
    
    # Send 5 requests - all should succeed
    for i in range(5):
        resp = client.post(
            "/api/v1/webhooks/tradingview",
            json={"test": f"signal_{i}"},
            headers={"X-TradingView-Secret": settings.tradingview_shared_secret},
        )
        # Should get 200, 400, or 409 (valid responses), NOT 429
        assert resp.status_code in [200, 400, 409, 500], f"Request {i+1} failed with {resp.status_code}"
    
    # 6th request should be rate limited (429)
    resp = client.post(
        "/api/v1/webhooks/tradingview",
        json={"test": "signal_6"},
        headers={"X-TradingView-Secret": settings.tradingview_shared_secret},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers or "retry-after" in resp.headers.keys()


def test_webhook_rate_limit_response_headers(client: TestClient, monkeypatch):
    """Test 429 response includes rate limit headers."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 1)
    
    # First request succeeds
    resp1 = client.post(
        "/api/v1/webhooks/tradingview",
        json={"test": "signal_1"},
        headers={"X-TradingView-Secret": settings.tradingview_shared_secret},
    )
    assert resp1.status_code in [200, 400, 409, 500]
    
    # Second request hits rate limit
    resp2 = client.post(
        "/api/v1/webhooks/tradingview",
        json={"test": "signal_2"},
        headers={"X-TradingView-Secret": settings.tradingview_shared_secret},
    )
    assert resp2.status_code == 429
    
    # Check for rate limit headers (case-insensitive)
    headers_lower = {k.lower(): v for k, v in resp2.headers.items()}
    assert "retry-after" in headers_lower or "x-ratelimit-limit" in headers_lower


def test_webhook_rate_limit_per_ip(client: TestClient, monkeypatch):
    """Test rate limiting is per IP address."""
    monkeypatch.setattr(settings, "webhook_rate_limit", 2)
    
    # Send 2 requests from default test IP (127.0.0.1)
    for i in range(2):
        resp = client.post(
            "/api/v1/webhooks/tradingview",
            json={"test": f"signal_{i}"},
            headers={"X-TradingView-Secret": settings.tradingview_shared_secret},
        )
        assert resp.status_code in [200, 400, 409, 500]
    
    # 3rd request from same IP should be blocked
    resp = client.post(
        "/api/v1/webhooks/tradingview",
        json={"test": "signal_3"},
        headers={"X-TradingView-Secret": settings.tradingview_shared_secret},
    )
    assert resp.status_code == 429


def test_default_rate_limit_is_50(client: TestClient):
    """Test default webhook_rate_limit is 50 requests/minute."""
    assert settings.webhook_rate_limit == 50
```

- [ ] **Step 2: Verify file exists**

Run:
```bash
ls -l /Users/minhhq/Documents/telegram-signal-bot/tests/integration/test_webhook_rate_limiting.py
```

Expected: File exists and is readable

- [ ] **Step 3: Run tests to verify they pass**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m pytest tests/integration/test_webhook_rate_limiting.py -v --rootdir=/Users/minhhq/Documents/telegram-signal-bot
```

Expected: All 4 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_webhook_rate_limiting.py
git commit -m "test: add integration tests for webhook rate limiting"
```

---

## Task T8: Verify full test suite passes

**Files:** None (verification only)

- [ ] **Step 1: Run unit tests**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m pytest tests/unit -v --rootdir=/Users/minhhq/Documents/telegram-signal-bot 2>&1 | tail -5
```

Expected: All unit tests pass (should see "X passed")

- [ ] **Step 2: Run integration tests**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m pytest tests/integration -v --rootdir=/Users/minhhq/Documents/telegram-signal-bot 2>&1 | tail -5
```

Expected: All integration tests pass, including the new rate limiting tests

- [ ] **Step 3: Run full test suite**

Run:
```bash
/Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m pytest tests/ --tb=short --rootdir=/Users/minhhq/Documents/telegram-signal-bot 2>&1 | tail -3
```

Expected: All tests pass (e.g., "74 passed in 52s")

- [ ] **Step 4: Commit if any fixes needed**

If all tests already pass, no commit needed. If fixes were required, commit them:

```bash
git status
```

If there are uncommitted changes, commit them with appropriate message.

---

## Task T9: Manual smoke test (optional but recommended)

**Files:** None (testing only)

- [ ] **Step 1: Start the app locally**

Run:
```bash
cd /Users/minhhq/Documents/telegram-signal-bot && /Users/minhhq/Documents/telegram-signal-bot/.venv/bin/python3.13 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
```

Wait 2 seconds for app to start.

- [ ] **Step 2: Send test webhook requests**

Open another terminal and send rapid requests:

```bash
for i in {1..52}; do
  curl -X POST http://127.0.0.1:8000/api/v1/webhooks/tradingview \
    -H "Content-Type: application/json" \
    -H "X-TradingView-Secret: test-secret" \
    -d "{\"test\": \"signal_$i\"}" \
    -w "Request %i: Status %{http_code}\n" 2>/dev/null
  sleep 0.01
done
```

Expected output shows:
- Requests 1-50: Mix of 200, 400, 409, 500 responses
- Request 51-52: Status 429 (rate limited)

- [ ] **Step 3: Stop the app**

```bash
pkill -f "uvicorn app.main"
```

---

## Verification Checklist

Before considering the implementation complete:

- [ ] All 9 tasks completed
- [ ] All commits created with clear messages
- [ ] Full test suite passes (unit + integration)
- [ ] Rate limiter decorator applied to webhook endpoint
- [ ] Configuration via WEBHOOK_RATE_LIMIT env var working
- [ ] HTTP 429 response when limit exceeded
- [ ] Rate limiting is per IP address
- [ ] Default limit is 50 requests/minute
- [ ] No performance regression on normal requests

---

## Success Criteria (from Spec)

- ✅ Webhook endpoint rate-limited to 50 requests/minute per IP
- ✅ HTTP 429 response when exceeded
- ✅ Configuration via `WEBHOOK_RATE_LIMIT` env var
- ✅ All tests pass
- ✅ No performance impact on normal requests (<1ms overhead)
