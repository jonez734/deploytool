PROJECT = deploytool
OUTDIR = dist/
VERSION := $(shell date +%Y%m%d%H%M)
WHEEL := $(OUTDIR)$(PROJECT)-0.0.1.dev$(VERSION)-py3-none-any.whl

PYTHON ?= python3
VENV_DIR ?= $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV),.venv)
VENV_OWNER ?= $(USER)
VENV_GROUP ?= $(USER)

PIP ?= $(PYTHON) -m pip

.PHONY: all clean build version install deploy-tui install-venv uninstall-venv test

all: help

help:
	@echo "$(PROJECT) - Deploy tool for zoidtechnologies.com projects"
	@echo ""
	@echo "Targets:"
	@echo "  version  Stamp src/$(PROJECT)/_version.py with date + git hash"
	@echo "  build    Build sdist+wheel into $(OUTDIR)"
	@echo "  install  Install built wheel from $(OUTDIR) into active venv"
	@echo "  test     Run pytest tests/"
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

# DEPLOY_EDITABLE is set by `deploytool --editable`. When unset,
# deploy-tui installs deploytool from the freshly-built wheel in
# $(OUTDIR). When set, it installs editable from the source tree.
# Note: deploytool's $(OUTDIR) is `dist/` (local), not
# `/srv/repo/deploytool/` — deploytool is a standalone repo
# and publishes to PyPI from dist/, not to the per-project
# /srv/repo/ OUTDIR that Phase 0 introduced for the other
# projects.
DEPLOY_EDITABLE ?=

# DEPLOY_UPGRADE is set by `deploytool --upgrade` (default true) and
# unset by `--no-upgrade`. When "1", `pip install` invocations below
# pass `--upgrade` so the install replaces any prior version of the
# same distribution and pulls the newest transitive deps from PyPI.
# When empty, the prior behavior holds: pip is a no-op if the wheel
# version already matches what's installed, and transitive deps are
# whatever was in the target venv at deploy time. The install-venv
# block always upgrades `pip` itself (`pip install --upgrade pip`) —
# that's not gated on DEPLOY_UPGRADE because a stale `pip` breaks
# everything downstream and is unrelated to the project's wheel
# install.
DEPLOY_UPGRADE ?=
PIP_UPGRADE_FLAG := $(if $(filter 1,$(DEPLOY_UPGRADE)),--upgrade,)
install: build
ifeq ($(DEPLOY_EDITABLE),1)
	cd src && $(PIP) install $(PIP_UPGRADE_FLAG) --no-cache-dir -e .
	-rm -rf src/$(PROJECT).egg-info
else
	$(PIP) install $(PIP_UPGRADE_FLAG) --no-deps $(WHEEL)
	@$(VERIFY_INSTALL)
endif

# Verify that the wheel just installed is the one `pip show` reports
# as installed. Catches the silent-no-op case where `pip install <wheel>`
# exits 0 without actually replacing an existing install (different
# venv, orphaned .dist-info, permission-denied mid-install, etc.). On
# mismatch, prints the verbatim `pip show` output (stdout) and aborts
# the deploy with a summary (stderr). Mirrors the reference
# implementation in zoidoffice/src/Makefile.
#
# Three values are compared:
#   - filename:  regex-extracted from the wheel filename
#   - METADATA:  Version: line from the wheel's METADATA (unzip -p)
#   - pip show:  Version: line from `pip show $(PROJECT)` post-install
#
# All three must agree. Editable installs (DEPLOY_EDITABLE=1) skip
# this — `pip show` for an editable install reports the *source-tree*
# version, not a wheel version, and the comparison semantics differ.
VERIFY_INSTALL = \
	EXPECTED_FROM_FILENAME=$$(basename '$(WHEEL)' | sed -E 's/^$(PROJECT)-(.+)-py3-none-any\.whl$$/\1/'); \
	EXPECTED_FROM_METADATA=$$(unzip -p '$(WHEEL)' '*/METADATA' 2>/dev/null | awk -F': ' '/^Version: / {print $$2; exit}'); \
	echo "=== verify-install ($(PROJECT)) ==="; \
	echo "  wheel filename Version: $$EXPECTED_FROM_FILENAME"; \
	echo "  wheel METADATA Version: $$EXPECTED_FROM_METADATA"; \
	echo "--- pip show $(PROJECT) ---"; \
	SHOW_OUTPUT=$$($(PIP) show $(PROJECT) 2>&1); \
	SHOW_RC=$$?; \
	echo "$$SHOW_OUTPUT"; \
	echo "(pip show exited $$SHOW_RC)"; \
	echo "--- end pip show ---"; \
	INSTALLED=$$(echo "$$SHOW_OUTPUT" | awk '/^Version: / {print $$2; exit}'); \
	if [ "$$INSTALLED" != "$$EXPECTED_FROM_FILENAME" ] \
		|| [ "$$INSTALLED" != "$$EXPECTED_FROM_METADATA" ]; then \
		echo "verify-install FAILED: $(WHEEL) was installed but pip show does not agree" >&2; \
		echo "  expected filename:  $$EXPECTED_FROM_FILENAME" >&2; \
		echo "  expected METADATA:  $$EXPECTED_FROM_METADATA" >&2; \
		echo "  pip show Version:   $$INSTALLED" >&2; \
		exit 1; \
	fi; \
	echo "verify-install OK: pip show reports $$INSTALLED"

deploy-tui: install

test:
	$(PYTHON) -m pytest tests/

install-venv:
	@command -v sudo >/dev/null 2>&1 || { echo "Error: sudo required"; exit 1; }
	@sudo -u $(VENV_OWNER) test -d "$(VENV_DIR)" || sudo -u $(VENV_OWNER) $(PYTHON) -m venv "$(VENV_DIR)"
	sudo -u $(VENV_OWNER) $(VENV_DIR)/bin/pip install --upgrade pip
	sudo -u $(VENV_OWNER) $(VENV_DIR)/bin/pip install $(PIP_UPGRADE_FLAG) --quiet build setuptools wheel
	@echo "Ensured venv at $(VENV_DIR) (owner: $(VENV_OWNER):$(VENV_GROUP))"

uninstall-venv:
	@echo "WARNING: removing $(VENV_DIR) (this may delete your active venv)"
	-rm -rf $(VENV_DIR)
	@echo "Removed $(VENV_DIR)"
