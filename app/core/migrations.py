from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MIGRATIONS_DIR = ROOT / "migrations"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
MIGRATION_ADVISORY_LOCK_KEY: Final[int] = 1945035530


@dataclass(frozen=True)
class Migration:
    version: str
    filename: str
    path: Path
    checksum: str


def normalize_database_url(url: str) -> str:
    return (
        url.replace("postgresql+psycopg://", "postgresql://")
        .replace("postgres+psycopg://", "postgres://")
    )


def load_migrations(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(migrations_dir.glob("[0-9][0-9][0-9]_*.sql")):
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        version = path.stem.split("_", 1)[0]
        migrations.append(
            Migration(
                version=version,
                filename=path.name,
                path=path,
                checksum=checksum,
            )
        )
    if not migrations:
        raise RuntimeError(f"No migration files found in {migrations_dir}")
    return migrations


def ensure_schema_migrations_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} (
                version VARCHAR(32) PRIMARY KEY,
                filename TEXT NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def fetch_applied_migrations(conn: psycopg.Connection) -> dict[str, tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT version, filename, checksum FROM {SCHEMA_MIGRATIONS_TABLE} ORDER BY version"
        )
        rows = cur.fetchall()
    return {version: (filename, checksum) for version, filename, checksum in rows}


def apply_migration(conn: psycopg.Connection, migration: Migration) -> None:
    migration_sql = migration.path.read_text(encoding="utf-8")
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(migration_sql)
            cur.execute(
                sql.SQL(
                    "INSERT INTO {} (version, filename, checksum) VALUES (%s, %s, %s)"
                ).format(sql.Identifier(SCHEMA_MIGRATIONS_TABLE)),
                (migration.version, migration.filename, migration.checksum),
            )


_LOCK_TIMEOUT = "10s"


def acquire_migration_lock(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        # Set a session-level lock timeout so a stale lock doesn't block forever.
        # If pg_advisory_lock is held by a crashed process, this will fail after 10s
        # instead of waiting indefinitely.
        cur.execute(f"SET lock_timeout = '{_LOCK_TIMEOUT}'")
        cur.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))


def release_migration_lock(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_ADVISORY_LOCK_KEY,))



def apply_migrations_to_url(database_url: str, migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[str]:
    applied_now: list[str] = []
    migrations = load_migrations(migrations_dir)
    with psycopg.connect(normalize_database_url(database_url), autocommit=False) as conn:
        acquire_migration_lock(conn)
        try:
            ensure_schema_migrations_table(conn)
            applied = fetch_applied_migrations(conn)
            for migration in migrations:
                if migration.version in applied:
                    applied_filename, applied_checksum = applied[migration.version]
                    if applied_checksum != migration.checksum:
                        raise RuntimeError(
                            f"Checksum mismatch for version {migration.version}: "
                            f"db has {applied_filename} / {applied_checksum}, file has {migration.filename} / {migration.checksum}"
                        )
                    continue
                apply_migration(conn, migration)
                applied_now.append(f"{migration.version} {migration.filename}")
        finally:
            release_migration_lock(conn)
            conn.commit()
    return applied_now


def migration_status(database_url: str, migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> list[tuple[str, str, str]]:
    migrations = load_migrations(migrations_dir)
    with psycopg.connect(normalize_database_url(database_url), autocommit=False) as conn:
        ensure_schema_migrations_table(conn)
        applied = fetch_applied_migrations(conn)
        return [
            ("applied" if migration.version in applied else "pending", migration.version, migration.filename)
            for migration in migrations
        ]
