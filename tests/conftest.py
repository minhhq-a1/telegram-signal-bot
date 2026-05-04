"""Root conftest: set required env vars before any app module is imported."""
from __future__ import annotations

import os

os.environ.setdefault("tradingview_shared_secret", "test-secret")
os.environ.setdefault("database_url", "postgresql+psycopg://ignored:ignored@localhost/ignored")
os.environ.setdefault("telegram_bot_token", "test-token")
os.environ.setdefault("telegram_main_chat_id", "main-chat")
os.environ.setdefault("telegram_warn_chat_id", "warn-chat")
os.environ.setdefault("telegram_admin_chat_id", "admin-chat")
os.environ.setdefault("dashboard_token", "test-dash-token")
