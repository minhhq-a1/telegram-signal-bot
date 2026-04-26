from __future__ import annotations

from sqlalchemy import text


def test_db_fixture_bootstraps_seed_data_from_migration(db_session):
    row = db_session.execute(
        text("SELECT config_value FROM system_configs WHERE config_key = 'signal_bot_config'")
    ).first()

    assert row is not None
    assert row[0]["allowed_symbols"] == ["BTCUSDT", "BTCUSD"]


def test_db_fixture_reapplies_migration_for_next_test_session(db_session):
    row = db_session.execute(
        text("SELECT config_value FROM system_configs WHERE config_key = 'signal_bot_config'")
    ).first()

    assert row is not None
    assert row[0]["enable_news_block"] is True
