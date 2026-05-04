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


def test_db_fixture_tracks_versioned_migrations(db_session):
    rows = db_session.execute(
        text("SELECT version, filename FROM schema_migrations ORDER BY version")
    ).all()

    assert rows == [
        ("001", "001_init.sql"),
        ("002", "002_add_ops_migration_baseline.sql"),
        ("003", "003_v11_upgrade.sql"),
        ("004", "004_query_indexes.sql"),
        ("005", "005_v11_config_idempotency_repair.sql"),
        ("006", "006_v12_observability.sql"),
        ("007", "007_v12_signal_outcomes.sql"),
        ("008", "008_v12_config_audit.sql"),
        ("009", "009_v12_market_context.sql"),
        ("010", "010_v13_market_context_index.sql"),
    ]


def test_db_fixture_bootstraps_ops_baseline_config(db_session):
    row = db_session.execute(
        text("SELECT config_value FROM system_configs WHERE config_key = 'db_ops_baseline'")
    ).first()

    assert row is not None
    assert row[0]["migration_strategy"] == "raw_sql_versioned"
    assert row[0]["requires_restore_drill"] is True
