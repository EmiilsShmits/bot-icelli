# bot-icelli: every common command. `make help` lists them. Run from the repo root.
SHELL := /bin/bash
AALTO := third_party/aaltonomous-humanoid
VENV  := .venv
PY    := $(VENV)/bin/python
# First Python >= 3.10 on PATH; override with: make setup PYTHON=/path/to/python3.12
PYTHON ?= $(shell for p in python3.13 python3.12 python3.11 python3.10 python3; do command -v $$p >/dev/null 2>&1 && { echo $$p; break; }; done)
export PYTHONPATH := $(CURDIR)/$(AALTO)

PORT    ?= 8000
POLICY  ?= hold
TEAM    ?= bot-icelli
TASK    ?= sort_fixed
TRIALS  ?= 10
IMAGE   ?= bot-icelli/policy:dev
SIM_CONTAINER ?= aalto

.DEFAULT_GOAL := help
.PHONY: help setup serve check mock docker-build docker-check eval update-aalto clean

help: ## list commands
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  make %-14s %s\n", $$1, $$2}'

setup: ## init the Aalto submodule + .venv with policy and test deps (Python >= 3.10)
	git submodule update --init --recursive
	@$(PYTHON) -c 'import sys; v=sys.version_info; sys.exit(0 if v >= (3,10) else f"Need Python >= 3.10, found {v.major}.{v.minor}. Run: make setup PYTHON=/path/to/python3.12")'
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r policy/requirements-dev.txt
	@echo "setup done. Next: make check"

serve: ## run our policy server on :8000 (POLICY=hold; Ctrl-C to stop)
	$(PY) policy/server.py --policy $(POLICY) --port $(PORT)

check: ## plumbing test: Aalto synthetic replay against our server (shapes + >= 27 Hz)
	PY=$(PY) PORT=$(PORT) POLICY=$(POLICY) bash policy/check.sh replay

mock: ## 2 full episodes on Aalto's mock backend (runner + safety filter, no GPU); logs in artifacts/runs/
	PY=$(PY) PORT=$(PORT) POLICY=$(POLICY) TEAM=$(TEAM) bash policy/check.sh mock

docker-build: ## build the submission image for linux/amd64 (IMAGE=bot-icelli/policy:dev POLICY=hold)
	docker buildx build --platform linux/amd64 -f policy/Dockerfile --build-arg POLICY=$(POLICY) -t $(IMAGE) --load .

docker-check: ## replay test against the built image; also checks startup < 120 s (GPUS=none on a CPU-only host)
	$(PY) -m aaltonomous.deploy.replay --synthetic 100 --container $(IMAGE) --gpus $(or $(GPUS),all)

eval: ## score a running policy (:8000) in Isaac sim. Run on the Verda sim host with the aalto container up
	docker exec $(SIM_CONTAINER) aalto eval --policy ws://localhost:$(PORT) --team $(TEAM) --task $(TASK) --trials $(TRIALS)

update-aalto: ## pull the latest Aalto starter repo into the submodule (then commit the new pointer)
	git submodule update --remote $(AALTO)
	@cd $(AALTO) && git log --oneline -5

clean: ## remove local test logs (keeps .venv and artifacts/ datasets)
	rm -rf artifacts/logs artifacts/runs
