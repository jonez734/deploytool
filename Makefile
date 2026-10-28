PROJECT = deploytool
OUTDIR = dist/
# Pinned with ?= so sub-make invocations (tui -> build, prod -> tui) share
# one version and the artifact names stay stable across stage and publish.
# Build version: 0.0.2.dev<YYYYMMDDHHMMSS>, unique per build (shared script in the meta-repo).
# Override WHEELS_DIR when building outside the meta-repo.
WHEELS_DIR ?= $(CURDIR)/../dist-wheels
VERSION_SCRIPT ?= $(CURDIR)/../scripts/next_version.sh
VERSION ?= $(shell $(VERSION_SCRIPT) 0.0.2.dev $(WHEELS_DIR))
WHEEL := $(OUTDIR)$(PROJECT)-$(VERSION)-py3-none-any.whl
# Artifact glob for this version. Publish targets upload only these files.
ARTIFACTS = $(OUTDIR)$(PROJECT)-$(VERSION)*

PYTHON ?= python3
VENV_DIR ?= $(if $(VIRTUAL_ENV),$(VIRTUAL_ENV),.venv)
VENV_OWNER ?= $(USER)
VENV_GROUP ?= $(USER)

PIP ?= $(PYTHON) -m pip

# Publish destination for `prod`. Overridable; empty makes `repo` refuse.
REPO_DEST ?= /srv/repo/deploytool/
# Upload targets refuse to run unless PYPI_CONFIRM=1 is set. Credentials
# come from TWINE_USERNAME=__token__ and TWINE_PASSWORD in the environment.
PYPI_CONFIRM ?=
TESTPYPI_URL = https://test.pypi.org/legacy/

.PHONY: all clean build stage check version install deploy-tui deploy prod repo \
	install-venv uninstall-venv test pypi testpypi require-repo-dest verify-tokens

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
	@echo '__version__ = "$(VERSION)"' > src/$(PROJECT)/_version.py
	@echo '__datestamp__ = "$(VERSION)"' >> src/$(PROJECT)/_version.py
	@echo '__githash__ = "'`git log -1 --format='%H' 2>/dev/null | cut -c 1-16`'"' >> src/$(PROJECT)/_version.py
	@cat src/$(PROJECT)/_version.py

build: version
	cd src && $(PYTHON) -m build --outdir ../$(OUTDIR)

# Build artifacts only. Used by every install and publish path.
stage: build

# Validate the built artifacts with twine before any publish.
check: stage
	$(PYTHON) -m twine check $(ARTIFACTS)*

# DEPLOY_EDITABLE is set by `deploytool --editable`. When unset,
# deploy-tui installs deploytool from the freshly-built wheel in
# $(OUTDIR). When set, it installs editable from the source tree.
# $(OUTDIR) is the local `dist/`; `prod` publishes a copy to
# $(REPO_DEST) (default /srv/repo/deploytool/) and `pypi`/`testpypi`
# upload to the package indexes. Nothing here uploads implicitly.
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

# Operator-side install into the active venv. Default `deploy` target.
deploy-tui: install

deploy: deploy-tui

# Publish: install into the venv (tui), then copy this version's artifacts
# to $(REPO_DEST). The only target that writes outside dist/ and the venv.
prod: deploy-tui repo

# Refuse before any build work when REPO_DEST is unset.
require-repo-dest:
	@test -n "$(REPO_DEST)" || { echo "repo: REPO_DEST is not set; nothing published" >&2; exit 1; }

# rsync this version's artifacts to $(REPO_DEST). Only target that touches
# /srv/repo, and it runs only from `prod`.
repo: require-repo-dest stage
	rsync -av $(ARTIFACTS)* $(REPO_DEST)

# Credential and confirmation guard for index uploads.
verify-tokens:
	@test -n "$$TWINE_PASSWORD" || { \
		echo "Error: TWINE_PASSWORD is not set. Set TWINE_USERNAME=__token__ and TWINE_PASSWORD=<token>." >&2; exit 1; }
	@test "$${TWINE_USERNAME:-}" = "__token__" || { \
		echo "Error: TWINE_USERNAME must be __token__ for token auth." >&2; exit 1; }

# Upload to TestPyPI. Run this before `pypi`.
testpypi: check
	@test "$(PYPI_CONFIRM)" = "1" || { echo "testpypi: set PYPI_CONFIRM=1 to upload" >&2; exit 1; }
	@$(MAKE) --no-print-directory verify-tokens
	$(PYTHON) -m twine upload --repository-url $(TESTPYPI_URL) $(ARTIFACTS)*

# Upload to PyPI. Requires PYPI_CONFIRM=1.
pypi: check
	@test "$(PYPI_CONFIRM)" = "1" || { echo "pypi: set PYPI_CONFIRM=1 to upload" >&2; exit 1; }
	@$(MAKE) --no-print-directory verify-tokens
	$(PYTHON) -m twine upload $(ARTIFACTS)*

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
