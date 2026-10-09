.PHONY: test test-stdlib db-up db-down
# Python 3.12 + numpy + pandas required.
test:
	python -m pytest
# Same tests without pytest (what was used in the initial sandbox session)
test-stdlib:
	PYTHONPATH=services/technical-analysis:services/market-data python -m unittest discover -s services/technical-analysis/tests
	PYTHONPATH=services/technical-analysis:services/market-data python -m unittest discover -s services/market-data/tests
	PYTHONPATH=services/portfolio-analytics python -m unittest discover -s services/portfolio-analytics/tests
	PYTHONPATH=services/technical-analysis:services/signal-engine python -m unittest discover -s services/signal-engine/tests
	PYTHONPATH=services/backtesting python -m unittest discover -s services/backtesting/tests
	PYTHONPATH=services/pattern-recognition python -m unittest discover -s services/pattern-recognition/tests
	PYTHONPATH=services/technical-analysis:services/market-data:services/portfolio-analytics:services/signal-engine:services/backtesting python -m unittest discover -s tests/integration
db-up:
	docker compose up -d db
db-down:
	docker compose down
