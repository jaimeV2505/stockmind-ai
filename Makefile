.PHONY: test test-stdlib db-up db-down
# Python 3.12 + numpy + pandas required.
test:
	python -m pytest
# Same tests without pytest (what was used in the initial sandbox session)
test-stdlib:
	PYTHONPATH=services/technical-analysis:services/market-data python -m unittest discover -s services/technical-analysis/tests
	PYTHONPATH=services/technical-analysis:services/market-data python -m unittest discover -s services/market-data/tests
db-up:
	docker compose up -d db
db-down:
	docker compose down
