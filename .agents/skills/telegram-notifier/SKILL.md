---
name: telegram-notifier
description: "Implement or debug Telegram notification routing, retry behavior, and delivery status handling."
---

# Skill: Telegram Notifier
## Description
Implement hoặc debug `app/services/telegram_notifier.py` và Telegram delivery logic.
Trigger khi user đề cập: telegram, notifier, retry, send message, channel routing, MAIN/WARN/ADMIN channel, httpx, delivery status.

## Instructions

Đọc `app/services/telegram_notifier.py`, `tests/unit/test_telegram_notifier.py`, và `docs/CONVENTIONS.md` trước khi sửa logic.

---

### Interface hiện tại

```python
class TelegramNotifier:
    async def send_message(self, chat_id: str, text: str) -> dict:
        # POST Telegram API. Retry transient failures, raise nếu cuối cùng fail.

    async def notify(self, route: str, text: str) -> tuple[str, dict | None, str | None]:
        # route: "MAIN" | "WARN" | "ADMIN" | "NONE"
        # cũng accept legacy decision strings: "PASS_MAIN" | "PASS_WARNING"
        # returns: (delivery_status, telegram_response | None, error_detail | None)
        # KHÔNG raise exception ra caller.
```

### Channel routing

```python
def resolve_chat_id(self, route: str) -> str | None:
    if route in {"MAIN", "PASS_MAIN"}:
        return settings.telegram_main_chat_id
    if route in {"WARN", "PASS_WARNING"}:
        return settings.telegram_warn_chat_id
    if route == "ADMIN":
        return settings.telegram_admin_chat_id
    return None
```

```python
async def notify(self, route: str, text: str) -> tuple[str, dict | None, str | None]:
    if route == "NONE":
        return "SKIPPED", None, None

    chat_id = self.resolve_chat_id(route)
    if not chat_id:
        return "FAILED", None, f"No chat_id configured for route {route}"

    try:
        response = await self.send_message(chat_id, text)
        # enrich response with _telegram_message_id when Telegram returns result.message_id
        return "SENT", response, None
    except Exception as exc:
        return "FAILED", None, f"{type(exc).__name__}: {exc}"
```

### Retry policy trong `send_message()`

Code hiện tại retry trong `send_message()`, không dùng `_send_with_retry()` riêng.

```python
max_attempts = 4  # initial attempt + 3 retries
```

Retry behavior bắt buộc:

| Failure | Behavior |
|---|---|
| `httpx.TimeoutException` | retry exponential backoff `1s, 2s, 4s`, then raise |
| `httpx.RequestError` | retry exponential backoff `1s, 2s, 4s`, then raise |
| HTTP `429` | retry using `Retry-After` header; fallback `2 ** attempt`; then raise |
| HTTP `5xx` | retry exponential backoff `1s, 2s, 4s`, then raise |
| HTTP `4xx` except `429` | permanent failure; raise immediately, no retry |

**Quan trọng:**
- `send_message()` được phép raise sau khi hết retry.
- `notify()` phải catch exception và return `("FAILED", None, error_detail)`.
- Không log bot token hoặc secret.
- Delivery audit row được tạo ở `WebhookIngestionService.deliver_notification()`, không trong notifier.

### send_message implementation shape

```python
async def send_message(self, chat_id: str, text: str) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(4):
            try:
                response = await client.post(self.api_url, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                # 4xx non-429 no retry; 429/5xx retry if attempts remain
                ...
            except (httpx.TimeoutException, httpx.RequestError):
                # retry if attempts remain
                ...
```

### Verify

```bash
rtk python -m pytest tests/unit/test_telegram_notifier.py -v
```

Expected coverage:
- success first attempt
- timeout retry then success
- exhausted retries raises from `send_message()`
- `notify("NONE")` returns `SKIPPED`
- unknown route returns `FAILED`
- `notify()` catches send failure and returns `FAILED`
- 4xx non-429 is not retried
- 5xx and 429 are retried correctly
