from __future__ import annotations
import asyncio
import httpx
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_message(self, chat_id: str, text: str) -> dict:
        """
        POST to Telegram API with smart retry:
        - TimeoutException / RequestError: retry with exponential backoff (1s, 2s, 4s)
        - 429 Too Many Requests: retry using Retry-After header (fallback: exponential)
        - 5xx Server Error: retry with exponential backoff
        - 4xx (not 429): permanent failure — raise immediately, no retry
        """
        payload = {"chat_id": chat_id, "text": text}
        max_attempts = 4

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(max_attempts):
                try:
                    response = await client.post(self.api_url, json=payload)
                    response.raise_for_status()
                    return response.json()

                except httpx.HTTPStatusError as e:
                    status = e.response.status_code

                    if 400 <= status < 500 and status != 429:
                        logger.error(
                            "telegram_send_permanent_failure",
                            extra={"chat_id": chat_id, "status_code": status, "error": str(e)},
                        )
                        raise

                    if status == 429:
                        try:
                            sleep_secs = float(e.response.headers.get("Retry-After", ""))
                        except (ValueError, TypeError):
                            sleep_secs = 2 ** attempt
                        logger.warning(
                            "telegram_send_rate_limited",
                            extra={"chat_id": chat_id, "attempt": attempt + 1, "retry_after": sleep_secs},
                        )
                        if attempt < max_attempts - 1:
                            await asyncio.sleep(sleep_secs)
                            continue
                        logger.error("telegram_send_max_retries_reached", extra={"chat_id": chat_id})
                        raise

                    # 5xx — retry with exponential backoff
                    logger.warning(
                        "telegram_send_failed",
                        extra={"chat_id": chat_id, "attempt": attempt + 1, "error": str(e)},
                    )
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error("telegram_send_max_retries_reached", extra={"chat_id": chat_id})
                        raise

                except (httpx.TimeoutException, httpx.RequestError) as e:
                    logger.warning(
                        "telegram_send_failed",
                        extra={"chat_id": chat_id, "attempt": attempt + 1, "error": str(e)},
                    )
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error("telegram_send_max_retries_reached", extra={"chat_id": chat_id})
                        raise

    async def notify(self, route: str, text: str) -> tuple[str, dict | None, str | None]:
        """
        Route message tới đúng channel dựa theo TelegramRoute.
        returns: (DeliveryStatus string, telegram_api_response_dict | None, error_detail)
        """
        if route == "NONE":
            return ("SKIPPED", None, None)

        chat_id = self.resolve_chat_id(route)
            
        if not chat_id:
            logger.error("telegram_notify_skipped_no_chat_id", extra={"route": route})
            return ("FAILED", None, f"No chat_id configured for route {route}")

        try:
            resp = await self.send_message(chat_id, text)
            try:
                msg_id = str(resp.get("result", {}).get("message_id", ""))
                if msg_id:
                     resp["_telegram_message_id"] = msg_id
            except Exception:
                pass
            return ("SENT", resp, None)
        except Exception as exc:
            error_detail = f"{type(exc).__name__}: {exc}"
            logger.error("telegram_notify_failed", extra={"route": route, "error": error_detail})
            return ("FAILED", None, error_detail)

    def resolve_chat_id(self, route: str) -> str | None:
        if route in {"MAIN", "PASS_MAIN"}:
            return settings.telegram_main_chat_id
        if route in {"WARN", "PASS_WARNING"}:
            return settings.telegram_warn_chat_id
        if route == "ADMIN":
            return settings.telegram_admin_chat_id
        return None
