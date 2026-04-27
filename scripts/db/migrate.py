#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.migrations import DEFAULT_MIGRATIONS_DIR, apply_migrations_to_url, migration_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Versioned raw-SQL migration runner")
    parser.add_argument(
        "command",
        choices=["apply", "status"],
        help="Operation to run",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL") or os.environ.get("INTEGRATION_DATABASE_URL"),
        help="Database URL (defaults to DATABASE_URL or INTEGRATION_DATABASE_URL)",
    )
    parser.add_argument(
        "--migrations-dir",
        default=str(DEFAULT_MIGRATIONS_DIR),
        help="Directory containing versioned .sql migrations",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url is required when DATABASE_URL / INTEGRATION_DATABASE_URL is not set")

    migrations_dir = Path(args.migrations_dir).resolve()
    if args.command == "apply":
        applied_now = apply_migrations_to_url(args.database_url, migrations_dir)
        if applied_now:
            for item in applied_now:
                print(f"apply {item}")
        else:
            print("skip all migrations (already applied)")
        print("ok migrations applied")
        return 0

    for state, version, filename in migration_status(args.database_url, migrations_dir):
        print(f"{state:7} {version} {filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
