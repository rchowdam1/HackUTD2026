UV := env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV uv

.PHONY: install lint smoke test run preflight verify verify-changed verify-lint verify-formal demo-up demo

install:
	$(UV) sync

lint:
	$(UV) tool run ruff@0.17.4 check

test:
	$(UV) run pytest

smoke: install lint
	$(UV) run pytest
	$(UV) run python scripts/smoke_replay.py

run:
	$(UV) run uvicorn app.main:app --reload --port 8000

preflight: install
	scripts/preflight

demo-up: install
	scripts/demo_up

# Whole demo on one laptop; flags: make demo ARGS="--no-twilio" or ARGS="--tailnet"
demo: install
	scripts/demo $(ARGS)

# Verification (docs/verification.md): real app, isolated sandbox, evidence in .verify/runs/
VERIFY := $(UV) run --with playwright==1.64.1 python .agents/skills/verify-app/scripts/verify.py
BASE ?= origin/main

verify: install
	$(VERIFY) run $(ARGS)

verify-changed: install
	$(VERIFY) run --changed $(BASE) $(ARGS)

verify-lint:
	$(VERIFY) lint

verify-formal:
	.agents/skills/verify-pipeline-formal/scripts/check.sh $(ARGS)
