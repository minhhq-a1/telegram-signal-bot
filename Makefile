.PHONY: smoke-local test

smoke-local:
	bash ./scripts/smoke_local.sh

test:
	./.venv/bin/python -m pytest -q
