"""Unit tests for TelegramNotifier.send_message retry + exponential backoff."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import httpx
import pytest

from app.services.telegram_notifier import TelegramNotifier


def _make_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"ok": True, "result": {"message_id": 1}}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


async def test_send_message_success_first_attempt():
    notifier = TelegramNotifier()
    mock_resp = _make_response(200, {"ok": True, "result": {"message_id": 42}})

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        result = await notifier.send_message("chat-123", "hello")

    assert result == {"ok": True, "result": {"message_id": 42}}
    mock_sleep.assert_not_called()


async def test_send_message_retries_on_timeout_then_succeeds():
    notifier = TelegramNotifier()
    success_resp = _make_response(200, {"ok": True, "result": {"message_id": 99}})

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[
            httpx.TimeoutException("timeout"),
            httpx.TimeoutException("timeout"),
            success_resp,
        ])
        mock_client_cls.return_value = mock_client

        result = await notifier.send_message("chat-123", "hello")

    assert result == {"ok": True, "result": {"message_id": 99}}
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2**0
    mock_sleep.assert_any_call(2)  # 2**1


async def test_send_message_exhausts_retries_raises():
    notifier = TelegramNotifier()

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.TimeoutException("always timeout")
        )
        mock_client_cls.return_value = mock_client

        with pytest.raises(httpx.TimeoutException):
            await notifier.send_message("chat-123", "hello")

    # 4 attempts = 3 sleeps (no sleep after last attempt)
    assert mock_sleep.call_count == 3
    mock_sleep.assert_any_call(1)   # 2**0
    mock_sleep.assert_any_call(2)   # 2**1
    mock_sleep.assert_any_call(4)   # 2**2


async def test_send_message_retries_on_http_status_error():
    notifier = TelegramNotifier()
    success_resp = _make_response(200, {"ok": True, "result": {"message_id": 7}})
    error_resp = _make_response(429)

    with patch("httpx.AsyncClient") as mock_client_cls, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=[error_resp, success_resp])
        mock_client_cls.return_value = mock_client

        result = await notifier.send_message("chat-123", "hello")

    assert result["result"]["message_id"] == 7


async def test_notify_route_none_returns_skipped():
    notifier = TelegramNotifier()
    status, resp, err = await notifier.notify("NONE", "any text")
    assert status == "SKIPPED"
    assert resp is None
    assert err is None


async def test_notify_unknown_route_returns_failed():
    notifier = TelegramNotifier()
    status, resp, err = await notifier.notify("INVALID_ROUTE", "any text")
    assert status == "FAILED"
    assert resp is None
    assert err is not None
    assert "INVALID_ROUTE" in err


async def test_notify_success_returns_sent_with_message_id():
    notifier = TelegramNotifier()
    fake_api_response = {"ok": True, "result": {"message_id": 123}}

    with patch.object(notifier, "send_message", new=AsyncMock(return_value=fake_api_response)):
        status, resp, err = await notifier.notify("MAIN", "hello main")

    assert status == "SENT"
    assert err is None
    assert resp is not None
    assert resp["_telegram_message_id"] == "123"


async def test_notify_send_fails_returns_failed():
    notifier = TelegramNotifier()

    with patch.object(
        notifier,
        "send_message",
        new=AsyncMock(side_effect=httpx.TimeoutException("timed out")),
    ):
        status, resp, err = await notifier.notify("MAIN", "hello")

    assert status == "FAILED"
    assert resp is None
    assert err is not None
    assert "TimeoutException" in err
