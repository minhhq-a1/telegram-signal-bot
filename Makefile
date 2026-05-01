.PHONY: test-unit test-integration test smoke-local migrate db-migration-status restore-drill

test-unit:
	python3 -m pytest tests/unit -q

test-integration:
	python3 -m pytest tests/integration -q

test:
	python3 -m pytest -q

smoke-local:
	bash scripts/smoke_local.sh

migrate:
	python3 scripts/db/migrate.py apply

db-migration-status:
	python3 scripts/db/migrate.py status

restore-drill:
	bash scripts/db/restore_drill.sh
