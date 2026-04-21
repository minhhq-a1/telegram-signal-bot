# Skill: Telegram Notifier
## Description
Implement hoặc debug `app/services/telegram_notifier.py` và Telegram delivery logic.
Trigger khi user đề cập: telegram, notifier, retry, send message, channel routing, MAIN/WARN/ADMIN channel, httpx, delivery status.

## Instructions

---

### Interface

```python
class TelegramNotifier:
    async def send_message(self, chat_id: str, text: str) -> dict
        # Gửi 1 message, raise nếu fail (caller xử lý retry)

    async def notify(self, route: str, text: str) -> tuple[str, dict | None]
        # route: "MAIN" | "WARN" | "ADMIN" | "NONE"
        # returns: (DeliveryStatus, telegram_response | None)
        # KHÔNG raise exception — luôn trả tuple
```

### Channel routing

```python
ROUTE_TO_CHAT = {
    "MAIN": settings.telegram_main_chat_id,
    "WARN": settings.telegram_warn_chat_id,
    "ADMIN": settings.telegram_admin_chat_id,
}

async def notify(self, route: str, text: str) -> tuple[str, dict | None]:
    if route == "NONE":
        return "SKIPPED", None

    chat_id = ROUTE_TO_CHAT.get(route)
    if not chat_id:
        return "SKIPPED", None

    return await self._send_with_retry(chat_id, text)
```

### Retry logic — quan trọng

```python
async def _send_with_retry(
    self, chat_id: str, text: str, max_retries: int = 3
) -> tuple[str, dict | None]:
    last_error = None
    for attempt in range(max_retries):
        try:
            data = await self.send_message(chat_id, text)
            return "SENT", data
        except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s
    # Hết retry — return FAILED, không raise
    return "FAILED", None
```

**Quan trọng:**
- `asyncio.sleep(2 ** attempt)` → lần 1: 1s, lần 2: 2s, lần 3: 4s
- Sau max_retries: return `("FAILED", None)` — **không raise exception**
- Caller (webhook_controller) log lỗi và tiếp tục

### send_message implementation

```python
async def send_message(self, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, json={"chat_id": chat_id, "text": text})
        resp.raise_for_status()
        return resp.json()
```

### Viết test với respx mock

```python
import respx
import httpx
import re

@respx.mock
async def test_telegram_retry_success_on_second_attempt():
    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 42}})

    respx.post(re.compile(r"https://api\.telegram\.org/.*")).mock(
        side_effect=side_effect
    )

    notifier = TelegramNotifier()
    status, data = await notifier.notify("MAIN", "test")

    assert status == "SENT"
    assert data["result"]["message_id"] == 42
    assert call_count == 2


@respx.mock
async def test_telegram_fail_all_retries_returns_failed():
    respx.post(re.compile(r"https://api\.telegram\.org/.*")).mock(
        side_effect=httpx.TimeoutException("timeout")
    )

    notifier = TelegramNotifier()
    status, data = await notifier.notify("MAIN", "test")

    # KHÔNG raise — return tuple
    assert status == "FAILED"
    assert data is None


def test_telegram_route_none_returns_skipped():
    import asyncio
    notifier = TelegramNotifier()
    status, data = asyncio.run(notifier.notify("NONE", "test"))
    assert status == "SKIPPED"
    assert data is None
```

### Verify

```bash
python -m pytest tests/unit/test_telegram_notifier.py -v
# test_retry_success_on_second_attempt
# test_fail_all_retries_returns_failed
# test_route_none_returns_skipped
```
