PYTHON ?= python
BACKEND_DIR := backend

.PHONY: install install-dev test lint format format-check check ci

install:
	$(PYTHON) -m pip install -r $(BACKEND_DIR)/requirements.txt

install-dev:
	$(PYTHON) -m pip install -r $(BACKEND_DIR)/requirements-dev.txt

test:
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest

lint:
	cd $(BACKEND_DIR) && $(PYTHON) -m ruff check app tests main.py

format:
	cd $(BACKEND_DIR) && $(PYTHON) -m black app tests main.py

format-check:
	cd $(BACKEND_DIR) && $(PYTHON) -m black --check app tests main.py

check: lint format-check test

ci:
	cd $(BACKEND_DIR) && $(PYTHON) -m pip check
	cd $(BACKEND_DIR) && $(PYTHON) -m ruff check app tests main.py
	cd $(BACKEND_DIR) && $(PYTHON) -m black --check app tests main.py
	cd $(BACKEND_DIR) && $(PYTHON) -m pytest
