# ---- Configuration ----------------------------------------------------------
PYTHON := python3
VENV := .venv
SCRIPTS := $(VENV)/scripts
PIP := $(SCRIPTS)/pip
PY := $(SCRIPTS)/python
PYTEST := $(SCRIPTS)/pytest
RUFF := $(SCRIPTS)/ruff
BLACK := $(SCRIPTS)/black
MYPY := $(SCRIPTS)/mypy
APPSCRIPTS := ./scripts
# ---- Phonies ----------------------------------------------------------------
.PHONY: help setup venv install run test lint format typecheck clean distclean

help:   
	@echo ""
	@echo "Targets:"
	@echo "  make setup       - create venv and install deps (runtime + dev)"
	@echo "  make run         - run the FastMCP stdio server"
	@echo "  make test        - run linters and tests"
	@echo "  make lint        - run ruff and black --check"
	@echo "  make format      - run black formatting"
	@echo "  make typecheck   - run mypy"
	@echo "  make clean       - remove __pycache__ and build artifacts"
	@echo "  make distclean   - clean + remove venv"
	@echo ""

setup: venv install
venv:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(PIP) install --upgrade pip wheel setuptools

install:
	@$(PIP) install -r requirements.txt
	@$(PIP) install -e ".[dev]"

run:
	@bash ./scripts/run_server.sh

test: lint
	@$(PYTEST)

lint:
	@$(RUFF) check .
	@$(BLACK) --check .

format:
	@$(BLACK) .

typecheck:
	@$(MYPY) .

clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@rm -rf .pytest_cache .mypy_cache build dist *.egg-info

distclean: clean
	@rm -rf $(VENV)

run-http:
    @$(APPSCRIPTS)/run_http.sh
