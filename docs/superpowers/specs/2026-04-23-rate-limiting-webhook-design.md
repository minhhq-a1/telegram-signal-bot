# Rate Limiting for Webhook Endpoint — Design Spec

**Date:** 2026-04-23  
**Issue:** #11 from code review backlog  
**Priority:** Low  
**Status:** Design phase

---

## Overview

Add per-IP rate limiting to the TradingView webhook endpoint (`POST /api/v1/webhooks/tradingview`) to prevent flood attacks and misconfiguration-induced spam. Protects `webhook_events` table from being overwhelmed with duplicate/spam requests.

**Key Decision:** Use `slowapi` library (HTTP rate limiter for FastAPI) with per-IP tracking, 50 requests/minute limit, HTTP 429 response, environment variable configuration.

---

## Requirements

| Requirement | Value |
|-------------|-------|
| Endpoint protected | `POST /api/v1/webhooks/tradingview` only |
| Rate limit strategy | Per IP address |
| Limit threshold | 50 requests/minute |
| Rate limit response | HTTP 429 (Too Many Requests) |
| Configuration method | Environment variable `WEBHOOK_RATE_LIMIT` |
| Default value | 50 (requests/minute) |

---

## Architecture

**Components:**

1. **Limiter instance** (`app/api/rate_limiter.py`)
   - Initialize `slowapi.Limiter` with `get_remote_address` key function
   - Extracts IP from `Request.client.host`
   - Tracks per-IP request counts in-memory with 1-minute sliding window

2. **Configuration** (`app/core/config.py`)
   - Add `webhook_rate_limit: int` field to Settings
   - Read from env var `WEBHOOK_RATE_LIMIT` (default: 50)
   - Pydantic validates as positive integer

3. **Decorator application** (`app/api/webhook_controller.py`)
   - Apply `@limiter.limit(f"{settings.webhook_rate_limit}/minute")` to webhook handler
   - slowapi intercepts requests, checks IP count, allows/denies per limit

4. **Error handling**
   - slowapi automatically raises `HTTPException(429)` when limit exceeded
   - Response includes `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining` headers
   - FastAPI serializes as JSON error response

---

## Data Flow

```
Request → Limiter checks IP count → Count < limit? 
  ├─ YES: Allow through → handler executes → 200/400/409/500 response
  └─ NO: Reject → HTTPException(429) → JSON error + headers
```

**Example sequence (51st request from same IP):**
```
GET /api/v1/webhooks/tradingview (from IP 192.168.1.1)
↓
Limiter: "192.168.1.1 has 50 requests in last minute"
↓
Raise HTTPException(status_code=429, detail="Rate limit exceeded")
↓
Response: 429 with headers {Retry-After: 60, X-RateLimit-Limit: 50, X-RateLimit-Remaining: 0}
```

---

## Implementation Details

**File changes:**

1. **`app/api/rate_limiter.py`** (NEW)
   ```python
   from slowapi import Limiter
   from slowapi.util import get_remote_address

   limiter = Limiter(key_func=get_remote_address)
   ```

2. **`app/core/config.py`** (MODIFY)
   ```python
   class Settings(BaseSettings):
       ...
       webhook_rate_limit: int = Field(default=50, env="WEBHOOK_RATE_LIMIT")
   ```

3. **`app/api/webhook_controller.py`** (MODIFY)
   ```python
   from app.api.rate_limiter import limiter
   
   @router.post(
       "/api/v1/webhooks/tradingview",
       ...
   )
   @limiter.limit("{settings.webhook_rate_limit}/minute")
   async def handle_tradingview_webhook(...):
       ...
   ```

4. **`app/main.py`** (MODIFY)
   ```python
   from app.api.rate_limiter import limiter
   
   app = FastAPI(...)
   app.state.limiter = limiter
   app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
   ```

5. **`.env.example`** (MODIFY - add documentation)
   ```
   # Rate limiting for webhook endpoint (requests per minute per IP)
   WEBHOOK_RATE_LIMIT=50
   ```

---

## Error Handling

**When rate limit exceeded:**

- Status: `429 Too Many Requests`
- Headers: `Retry-After`, `X-RateLimit-*` (added by slowapi)
- Body: JSON error (FastAPI default: `{"detail": "Rate limit exceeded"}`)

**Edge cases:**

- Multiple IPs: Each IP has independent 50-req/min counter ✅
- Rapid requests from same IP: slowapi tracks with sliding window ✅
- Configuration changes: `WEBHOOK_RATE_LIMIT` env var read at startup (no runtime refresh needed for MVP)
- In-memory storage: Lost on server restart (acceptable for MVP; could upgrade to Redis later)

---

## Testing Strategy

**Unit tests:**
- Mock `limiter` and verify decorator is applied
- Mock `settings.webhook_rate_limit` and test various values (0, 1, 50, 100)
- Test error response format (429 status, headers present)

**Integration tests:**
- Send 50 requests in rapid succession (should all pass)
- Send 51st request (should return 429)
- Wait for rate window reset, send again (should pass)
- Test from different IPs (each has independent limit)

**Configuration tests:**
- Override `WEBHOOK_RATE_LIMIT` env var, verify applied
- Default to 50 when env var not set

---

## Deployment & Operations

**Configuration:**
- Set `WEBHOOK_RATE_LIMIT=50` in production `.env`
- Adjust if needed (e.g., TradingView changes frequency)

**Monitoring:**
- Log 429 responses (optional, can add later if needed)
- Monitor `X-RateLimit-Remaining` headers to detect approaching limits

**Rollback:**
- Remove `@limiter.limit()` decorator, restart
- Or set `WEBHOOK_RATE_LIMIT=999999` (effectively disable)

---

## Dependencies

**New package:** `slowapi>=0.1.9`
- FastAPI/Starlette rate limiter
- Battle-tested, maintained
- Zero breaking changes expected during MVP phase

---

## Success Criteria

✅ Webhook endpoint rate-limited to 50 requests/minute per IP  
✅ HTTP 429 response when exceeded  
✅ Configuration via `WEBHOOK_RATE_LIMIT` env var  
✅ All tests pass  
✅ No performance impact on normal requests (<1ms overhead per request)  

---

## Out of Scope (Future)

- Distributed rate limiting across multiple server instances (would need Redis)
- Rate limiting on other endpoints (only webhook for now)
- User-based or token-based limits (IP-based only)
- Custom error response body format
- Admin dashboard for rate limit metrics
