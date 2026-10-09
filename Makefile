.PHONY: test test-stdlib db-up db-down
# Python 3.12 + numpy + pandas required.
test:
	python -m pytest
# Same tests without pytest (what was used in the initial sandbox session)
test-stdlib:
	./scripts/run_stdlib_tests.sh
db-up:
	docker compose up -d db
db-down:
	docker compose down
