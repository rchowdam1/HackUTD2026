UV := env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv

.PHONY: install smoke test run preflight

install:
	$(UV) sync

test:
	$(UV) run pytest

smoke: install
	$(UV) run pytest
	$(UV) run python scripts/smoke_replay.py

run:
	$(UV) run uvicorn app.main:app --reload --port 8000

preflight: install
	scripts/preflight
