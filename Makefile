.PHONY: smoke-local test db-migrate db-migration-status restore-drill

smoke-local:
	bash ./scripts/smoke_local.sh

test:
	./.venv/bin/python -m pytest -q

db-migrate:
	./.venv/bin/python scripts/db/migrate.py apply

db-migration-status:
	./.venv/bin/python scripts/db/migrate.py status

restore-drill:
	bash ./scripts/db/restore_drill.sh
