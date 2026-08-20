PROJECT = deploytool
OUTDIR = dist/
VERSION := $(shell date +%Y%m%d%H%M)
WHEEL := $(OUTDIR)$(PROJECT)-0.0.1.dev$(VERSION)-py3-none-any.whl

PYTHON ?= python3
VENV_DIR ?= $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV),.venv)
VENV_OWNER ?= $(USER)
VENV_GROUP ?= $(USER)

PIP ?= $(PYTHON) -m pip

.PHONY: all clean build version install deploy-tui install-venv uninstall-venv

all: help

help:
	@echo "$(PROJECT) - Deploy tool for zoidtechnologies.com projects"
	@echo ""
	@echo "Targets:"
	@echo "  version  Stamp src/$(PROJECT)/_version.py with date + git hash"
	@echo "  build    Build sdist+wheel into $(OUTDIR)"
	@echo "  install  Install built wheel from $(OUTDIR) into active venv"
	@echo "  clean    Remove build artifacts"

clean:
	-rm -rf build dist *.egg-info
	-find . -type d -name __pycache__ -exec rm -rf {} +

version:
	@mkdir -p src/$(PROJECT)
	@echo '__version__ = "0.0.1.dev$(VERSION)"' > src/$(PROJECT)/_version.py
	@echo '__datestamp__ = "$(VERSION)"' >> src/$(PROJECT)/_version.py
	@echo '__githash__ = "'`git log -1 --format='%H' 2>/dev/null | cut -c 1-16`'"' >> src/$(PROJECT)/_version.py
	@cat src/$(PROJECT)/_version.py

build: version
	cd src && $(PYTHON) -m build --outdir ../$(OUTDIR)

install: build
	$(PIP) install --no-deps $(WHEEL)

deploy-tui: install

install-venv:
	@command -v sudo >/dev/null 2>&1 || { echo "Error: sudo required"; exit 1; }
	@sudo -u $(VENV_OWNER) test -d "$(VENV_DIR)" || sudo -u $(VENV_OWNER) $(PYTHON) -m venv "$(VENV_DIR)"
	sudo -u $(VENV_OWNER) $(VENV_DIR)/bin/pip install --upgrade pip
	sudo -u $(VENV_OWNER) $(VENV_DIR)/bin/pip install --quiet build setuptools wheel
	@echo "Ensured venv at $(VENV_DIR) (owner: $(VENV_OWNER):$(VENV_GROUP))"

uninstall-venv:
	@echo "WARNING: removing $(VENV_DIR) (this may delete your active venv)"
	-rm -rf $(VENV_DIR)
	@echo "Removed $(VENV_DIR)"
