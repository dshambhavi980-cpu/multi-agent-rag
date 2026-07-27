.PHONY: install check contracts migrations api-check web-check test-e2e

install:
	python -m pip install -e "./apps/api[dev]"
	npm install

contracts:
	python scripts/check_contracts.py

migrations:
	python scripts/check_migrations.py

api-check:
	cd apps/api && python -m ruff check . && python -m ruff format --check . && python -m mypy app tests && python -m pytest

web-check:
	npm run check:web

check: contracts migrations api-check web-check

test-e2e:
	npm run test:e2e
