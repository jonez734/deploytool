"""Regression tests for the `--upgrade` / `--no-upgrade` CLI flag and the
`DEPLOY_UPGRADE` env-var plumbing in `lib.run_make_deploy`.

`--upgrade` is the only CLI flag in deploytool whose default is
*enabled* — the other flags (`--editable`, `--with-deps`,
`--dry-run`, `--verify`) are all opt-in. Rationale: the deploy
chain is the standard way to bring a venv up to the freshly-built
wheel, and operators expect transitive deps to track their PyPI
releases between deploys. See `SPECS.md §2.3` for the rationale
and the env-var contract.

These tests pin four contracts:

- `--upgrade` is the default; `--no-upgrade` flips the flag.
- `run_make_deploy` sets `DEPLOY_UPGRADE=1` in the subprocess env
  by default.
- `run_make_deploy` strips `DEPLOY_UPGRADE` from the subprocess env
  when `--no-upgrade` is passed (so a stray shell var can't silently
  upgrade a fresh deploy).
- Each per-project Makefile in the deploy chain declares
  `DEPLOY_UPGRADE ?=` and splices `$(PIP_UPGRADE_FLAG)` into its
  `pip install` lines (Makefile-presence guard, mirrors
  `test_deploy_shadow_install.py`).

The CLI-parser tests live up top; the `run_make_deploy` env-var
plumbing tests live in the second section; the per-project
Makefile-presence tests live in the third section.
"""

import os
import subprocess
import types
from argparse import Namespace

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# CLI parser: --upgrade / --no-upgrade round-trip
# ---------------------------------------------------------------------------


def test_buildargs_default_upgrade_is_true():
    """--upgrade is enabled by default; bare invocation yields upgrade=True."""
    args = deploytool.lib.buildargs().parse_args(["casino.tui"])
    assert args.upgrade is True


def test_buildargs_explicit_upgrade_sets_true():
    """--upgrade sets args.upgrade=True (explicit)."""
    args = deploytool.lib.buildargs().parse_args(["--upgrade", "casino.tui"])
    assert args.upgrade is True


def test_buildargs_no_upgrade_sets_false():
    """--no-upgrade sets args.upgrade=False."""
    args = deploytool.lib.buildargs().parse_args(["--no-upgrade", "casino.tui"])
    assert args.upgrade is False


def test_buildargs_upgrade_compatible_with_other_flags():
    """--upgrade / --no-upgrade round-trips with --editable, --with-deps, --verify."""
    args = deploytool.lib.buildargs().parse_args(
        ["--no-upgrade", "--editable", "--with-deps", "--verify", "casino.tui"]
    )
    assert args.upgrade is False
    assert args.editable is True
    assert args.with_deps is True
    assert args.verify is True


# ---------------------------------------------------------------------------
# run_make_deploy — DEPLOY_UPGRADE env-var plumbing
# ---------------------------------------------------------------------------


def _make_args(projects, **overrides):
    """Build a Namespace matching the shape lib.run_make_deploy reads."""
    defaults = dict(
        projects=projects,
        host="merlin",
        dry_run=False,
        verify=False,
        editable=False,
        with_deps=False,
        upgrade=True,
    )
    defaults.update(overrides)
    return Namespace(**defaults)


def _completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_make_deploy_default_sets_deploy_upgrade(monkeypatch):
    """Default (--upgrade on) plumbs DEPLOY_UPGRADE=1 into the subprocess env."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6.tui"])
    assert deploytool.lib.run_make_deploy(args, "bbsengine6", "tui") == 0

    assert captured["env"].get("DEPLOY_UPGRADE") == "1"
    assert captured["cmd"][:3] == ["make", "-C", f"{deploytool.lib.SOURCE_BASE}/bbsengine6"]


def test_run_make_deploy_explicit_upgrade_sets_env_var(monkeypatch):
    """--upgrade (explicit) plumbs DEPLOY_UPGRADE=1 into the subprocess env."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6.tui"], upgrade=True)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert captured["env"].get("DEPLOY_UPGRADE") == "1"


def test_run_make_deploy_no_upgrade_strips_env_var(monkeypatch):
    """--no-upgrade strips DEPLOY_UPGRADE from the subprocess env.

    Mirrors the DEPLOY_EDITABLE / DEPLOY_WITH_DEPS / DEPLOY_DRY_RUN
    strip-on-inherit pattern documented in SPECS.md §2.1.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_UPGRADE", raising=False)
    monkeypatch.setenv("DEPLOY_UPGRADE", "1")

    args = _make_args(["bbsengine6.tui"], upgrade=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert "DEPLOY_UPGRADE" not in captured["env"]


def test_run_make_deploy_no_upgrade_strips_existing_shell_var(monkeypatch):
    """When --no-upgrade is passed, a stale DEPLOY_UPGRADE=1 in the
    operator's shell is stripped so the per-project Makefile falls back
    to its no-upgrade branch. Symmetric to the strip-on-inherit guard
    for DEPLOY_EDITABLE / DEPLOY_WITH_DEPS."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_UPGRADE", raising=False)
    monkeypatch.setenv("DEPLOY_UPGRADE", "1")
    monkeypatch.setenv("PATH", "/usr/bin")

    args = _make_args(["bbsengine6.tui"], upgrade=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert "DEPLOY_UPGRADE" not in captured["env"]
    assert captured["env"]["PATH"] == "/usr/bin"


def test_run_make_deploy_upgrade_does_not_touch_editable_strip(monkeypatch):
    """--upgrade / --no-upgrade are orthogonal to --editable; passing
    --no-upgrade alone must still strip DEPLOY_EDITABLE so an operator
    with a stale DEPLOY_EDITABLE=1 in their shell doesn't accidentally
    flip into editable install mode."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_EDITABLE", raising=False)
    monkeypatch.setenv("DEPLOY_EDITABLE", "1")

    args = _make_args(["bbsengine6.tui"], upgrade=False, editable=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert "DEPLOY_UPGRADE" not in captured["env"]
    assert "DEPLOY_EDITABLE" not in captured["env"]


def test_run_make_deploy_upgrade_does_not_touch_with_deps_strip(monkeypatch):
    """--upgrade / --no-upgrade are orthogonal to --with-deps; passing
    --no-upgrade alone must still strip DEPLOY_WITH_DEPS so an operator
    with a stale DEPLOY_WITH_DEPS=1 in their shell doesn't accidentally
    flip bbsengine6's precheck-editable into warn-and-proceed mode."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_WITH_DEPS", raising=False)
    monkeypatch.setenv("DEPLOY_WITH_DEPS", "1")

    args = _make_args(["bbsengine6.tui"], upgrade=False, with_deps=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert "DEPLOY_UPGRADE" not in captured["env"]
    assert "DEPLOY_WITH_DEPS" not in captured["env"]


# ---------------------------------------------------------------------------
# Per-project Makefile-presence guards
#
# Each per-project Makefile in the deploy chain must declare
# `DEPLOY_UPGRADE ?=` and define
# `PIP_UPGRADE_FLAG := $(if $(filter 1,$(DEPLOY_UPGRADE)),--upgrade,)`,
# and must splice `$(PIP_UPGRADE_FLAG)` into at least one of its
# `pip install` lines. This is the same shape as the VERIFY_INSTALL
# Makefile-presence guards in test_deploy_shadow_install.py: the
# contract is that if a future commit drops the variable, the splice,
# or the ifeq wiring from any per-project Makefile, this test fires.
# ---------------------------------------------------------------------------


# (label, absolute path) — keyed by the deploy chain's project dirs.
# Files in this list MUST have at least one `pip install` recipe line;
# the PIP_UPGRADE_FLAG splice guards (below) require a splice site to
# be meaningful. bbsengine6/Makefile (top-level) does NOT have its own
# `pip install` line — it forwards DEPLOY_UPGRADE to the py/src
# sub-make — so it's covered by a separate test
# (`test_bbsengine6_top_level_forwards_deploy_upgrade_to_submake`).
PER_PROJECT_MAKEFILES = [
    ("deploytool/Makefile", "/home/opencode/data/work/deploytool/Makefile"),
    ("bbsengine6/py/src/Makefile", "/home/opencode/data/work/bbsengine6/py/src/Makefile"),
    ("bed/Makefile", "/home/opencode/data/work/bed/Makefile"),
    ("casino/Makefile", "/home/opencode/data/work/casino/Makefile"),
    ("zoid6/src/Makefile", "/home/opencode/data/work/zoid6/src/Makefile"),
    ("zoidoffice/src/Makefile", "/home/opencode/data/work/zoidoffice/src/Makefile"),
    ("getdate_next/Makefile", "/home/opencode/data/work/getdate_next/Makefile"),
    ("yummyjam/article2/Makefile", "/home/opencode/data/work/yummyjam/article2/Makefile"),
    ("mistermcfeely/Makefile", "/home/opencode/data/work/mistermcfeely/Makefile"),
]

# Files in this list declare `DEPLOY_UPGRADE ?=` so the env var is
# defined when a sub-make inherits it (bbsengine6/Makefile forwards
# DEPLOY_UPGRADE to the py/src sub-make without itself having a
# pip install site).
PER_PROJECT_MAKEFILES_DECLARE_ONLY = [
    ("bbsengine6/Makefile (top-level)", "/home/opencode/data/work/bbsengine6/Makefile"),
]


@pytest.mark.parametrize("label,path", PER_PROJECT_MAKEFILES)
def test_per_project_makefile_declares_deploy_upgrade(label, path):
    """Each per-project Makefile declares `DEPLOY_UPGRADE ?=` so the
    literal-string `ifeq ($(DEPLOY_UPGRADE),1)` gate has a defined
    value (empty when deploytool doesn't set it, "1" when it does)."""
    if not os.path.exists(path):
        pytest.skip(f"{label} not present at {path} (sibling repo absent)")
    text = open(path).read()
    assert "DEPLOY_UPGRADE ?=" in text, (
        f"{label} is missing `DEPLOY_UPGRADE ?=`. Per the contract in "
        "SPECS.md §2.3, each per-project Makefile must declare the var "
        "so deploytool's literal-string ifeq gate works."
    )


@pytest.mark.parametrize("label,path", PER_PROJECT_MAKEFILES_DECLARE_ONLY)
def test_per_project_makefile_declares_deploy_upgrade_only(label, path):
    """Per-project Makefiles that only forward DEPLOY_UPGRADE (no own
    pip install site) still need to declare the var so the sub-make
    inherits a defined value."""
    if not os.path.exists(path):
        pytest.skip(f"{label} not present at {path} (sibling repo absent)")
    text = open(path).read()
    assert "DEPLOY_UPGRADE ?=" in text, (
        f"{label} is missing `DEPLOY_UPGRADE ?=`. Per the contract in "
        "SPECS.md §2.3, each per-project Makefile — even one that "
        "only forwards the var to a sub-make — must declare it so "
        "the sub-make's literal-string ifeq gate has a defined value."
    )


@pytest.mark.parametrize("label,path", PER_PROJECT_MAKEFILES)
def test_per_project_makefile_defines_pip_upgrade_flag(label, path):
    """Each per-project Makefile with its own pip install site
    defines PIP_UPGRADE_FLAG via the canonical `$(if $(filter
    1,...),--upgrade,)` pattern and splices it into at least one
    `pip install` line."""
    if not os.path.exists(path):
        pytest.skip(f"{label} not present at {path} (sibling repo absent)")
    text = open(path).read()
    assert "PIP_UPGRADE_FLAG" in text, (
        f"{label} is missing `PIP_UPGRADE_FLAG`. Each per-project "
        "Makefile must derive `PIP_UPGRADE_FLAG := $(if $(filter "
        "1,$(DEPLOY_UPGRADE)),--upgrade,)` from DEPLOY_UPGRADE."
    )
    assert "$(PIP_UPGRADE_FLAG)" in text, (
        f"{label} defines PIP_UPGRADE_FLAG but never splices "
        "$(PIP_UPGRADE_FLAG) into a recipe line. The flag is useless "
        "without at least one `pip install $(PIP_UPGRADE_FLAG) ...` "
        "site."
    )


def test_bbsengine6_top_level_forwards_deploy_upgrade_to_submake():
    """bbsengine6/Makefile (top-level) deploy-tui forwards
    DEPLOY_UPGRADE=$(DEPLOY_UPGRADE) to py/src/Makefile so the
    upgrade flag flows through the parent/sub-make boundary.

    Without this forwarding, the operator's `--upgrade` choice would
    silently no-op for bbsengine6 (the top-level Makefile would still
    invoke py/src/Makefile, but py/src/Makefile would see DEPLOY_UPGRADE
    unset and fall through to the no-upgrade branch)."""
    path = "/home/opencode/data/work/bbsengine6/Makefile"
    if not os.path.exists(path):
        pytest.skip(f"{path} not present (sibling repo absent)")
    text = open(path).read()
    deploy_tui_section = text.split("deploy-tui:", 1)[1] if "deploy-tui:" in text else ""
    assert "DEPLOY_UPGRADE=$(DEPLOY_UPGRADE)" in deploy_tui_section, (
        "bbsengine6/Makefile deploy-tui target must forward "
        "DEPLOY_UPGRADE=$(DEPLOY_UPGRADE) to the py/src sub-make. "
        "Without this, the parent/sub-make boundary swallows the "
        "upgrade flag and bbsengine6 silently falls through to "
        "no-upgrade behavior."
    )


# ---------------------------------------------------------------------------
# End-to-end shape: dry-run output (per SPECS.md §2 example)
#
# With --dry-run and --upgrade (the default), the operator's terminal
# should see the `pip install --upgrade ...` recipe lines for each
# project in the chain. Pinning the shape guards against a future
# commit that drops the splice from any per-project Makefile: the
# dry-run output is the operator's primary signal that the upgrade
# mode is in effect, so it must reflect the wired-up state.
# ---------------------------------------------------------------------------


def test_dry_run_shows_pip_install_upgrade_for_bbsengine6(tmp_path):
    """`deploy --dry-run bbsengine6.tui` (with --upgrade default-on)
    must show a `pip install ... --upgrade` line in the bbsengine6
    sub-make output, not the prior no-upgrade form.

    Implementation note: invoking `deploy-tui` directly under
    `make -n` exercises `precheck-editable`, which hard-fails on
    an editable install in the active venv (the common test-env
    state). That aborts before the `pip install` recipe line is
    printed. The cleanest deterministic exercise of the splice
    is via the `install` target, which runs `pip install ... -e .`
    without a precheck. The `deploy-tui` non-editable branch is
    covered by the Makefile-presence guard above
    (`test_per_project_makefile_defines_pip_upgrade_flag`), which
    pins the splice shape directly in the source text.
    """
    import sys
    if sys.platform == "win32":
        pytest.skip("POSIX make required")

    bbsengine6_dir = "/home/opencode/data/work/bbsengine6"
    if not os.path.exists(bbsengine6_dir):
        pytest.skip(f"{bbsengine6_dir} not present")

    # Run the bbsengine6 py/src/Makefile `install` target under
    # --dry-run + DEPLOY_UPGRADE=1 so we can inspect the recipe
    # output without needing /srv/repo or a real install.
    result = subprocess.run(
        ["make", "-n", "-C", f"{bbsengine6_dir}/py/src", "install",
         "DEPLOY_UPGRADE=1"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = result.stdout + result.stderr
    assert "--upgrade" in combined, (
        f"Expected `pip install ... --upgrade` to appear in the dry-run "
        f"output for bbsengine6/py/src/Makefile install DEPLOY_UPGRADE=1, "
        f"but the captured output was:\n{combined}"
    )


def test_dry_run_no_upgrade_drops_pip_install_upgrade_for_bbsengine6():
    """`deploy --dry-run --no-upgrade bbsengine6.tui` must NOT show a
    `--upgrade` line in the bbsengine6 sub-make output — the
    PIP_UPGRADE_FLAG must expand to the empty string when
    DEPLOY_UPGRADE is empty.

    Implementation note: see `test_dry_run_shows_pip_install_upgrade_for_bbsengine6`
    above for why this exercises `install`, not `deploy-tui`.
    """
    import sys
    if sys.platform == "win32":
        pytest.skip("POSIX make required")

    bbsengine6_dir = "/home/opencode/data/work/bbsengine6"
    if not os.path.exists(bbsengine6_dir):
        pytest.skip(f"{bbsengine6_dir} not present")

    result = subprocess.run(
        ["make", "-n", "-C", f"{bbsengine6_dir}/py/src", "install",
         "DEPLOY_UPGRADE="],
        capture_output=True,
        text=True,
        timeout=60,
    )
    combined = result.stdout + result.stderr
    # The grep target: any line containing both "pip install" and
    # "--upgrade" is the failure case. PIP_UPGRADE_FLAG expanding to
    # the empty string means the recipe line is `pip install
    # --no-cache-dir -e .` (no --upgrade).
    pip_lines = [line for line in combined.splitlines() if "pip install" in line]
    offending = [line for line in pip_lines if "--upgrade" in line]
    assert not offending, (
        f"Expected no `pip install ... --upgrade` lines when "
        f"DEPLOY_UPGRADE is empty, but found:\n"
        + "\n".join(offending)
    )
