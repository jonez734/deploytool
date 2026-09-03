"""End-to-end regression coverage for the PEP 660 editable-shadow
failure mode on `deploy bbsengine6.tui`.

The shadow is *not* a pip-comparator issue: when an editable install
of `bbsengine6` already lives in the active venv, `pip install
<wheel>` writes a fresh `dist-info/` but the editable's
`__editable___bbsengine6_*_finder` `.pth` hook wins on `import`,
so the operator's TUI keeps loading source-tree code while `pip show`
reports the freshly-installed wheel version.

The shadow is caught in two layers (see
`bbsengine6/py/src/Makefile` `precheck-editable` and `verify-install`,
and `deploytool/SPECS.md` §2.2.1 for the DEPLOY_WITH_DEPS contract):

  - non-editable branch, --with-deps unset (default):
    `precheck-editable` bails with the editable source path and a
    pointer to the two clean remedies.
  - non-editable branch, --with-deps set:
    `precheck-editable` warns and proceeds; the post-install
    `verify-install` triple-check is the correctness contract.
  - editable branch (--editable): the editable is the intended state;
    no check, no fixup.

This file pins all four contracts so a regression that drops
`$(verify-install)` from `Makefile:186-187`, or removes the
`DEPLOY_WITH_DEPS` env-var plumbing in `lib.run_make_deploy`, can't
silently restore the silent-no-op.
"""

import subprocess as _std_subprocess
import types as _types
from argparse import Namespace as _Namespace

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# Helpers (mirror the shape used in tests/test_deploy_with_deps.py)
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
    )
    defaults.update(overrides)
    return _Namespace(**defaults)


def _completed(returncode=0, stdout="", stderr=""):
    return _types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _capture_io(monkeypatch):
    """Capture io.echo output (stdout path) for assertion on breadcrumbs."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )
    return msgs


# Pre-baked stderr from bbsengine6/py/src/Makefile precheck-editable,
# hard-fail branch (Makefile:148-163). The exit code is what deploytool
# surfaces; the breadcrumb is what the operator sees.
_EDITABLE_HARD_FAIL_STDERR = (
    "deploy-tui: bbsengine6 is installed editable in the active venv\n"
    "  editable source: /srv/repo/bbsengine6/py/src\n"
)

# Pre-baked stderr from bbsengine6/py/src/Makefile verify-install
# (Makefile:84-89). The exact text the operator sees when the
# editable .pth finder shadows the wheel install under --with-deps.
_VERIFY_INSTALL_FAILED_STDERR = (
    "verify-install FAILED: /srv/repo/bbsengine6/bbsengine6-"
    "0.0.1.dev20260830184512-py3-none-any.whl was installed but "
    "pip show does not agree\n"
    "  expected filename:  0.0.1.dev20260830184512\n"
    "  expected METADATA:  0.0.1.dev20260830184512\n"
    "  pip show Version:   0.0.1.dev20260828193001\n"
)

# Pre-baked stdout from a clean `make deploy-tui` run: wheel resolved,
# verify-install passed.
_CLEAN_DEPLOY_STDOUT = (
    "WHEEL=/srv/repo/bbsengine6/bbsengine6-0.0.1.dev20260830184512-"
    "py3-none-any.whl\n"
    "verify-install OK: pip show reports 0.0.1.dev20260830184512\n"
)


# ---------------------------------------------------------------------------
# non-editable + --with-deps unset → precheck-editable hard-fails
# ---------------------------------------------------------------------------


def test_shadow_install_fails_without_with_deps(monkeypatch):
    """Editable install + non-editable branch + no --with-deps: the Makefile
    precheck bails; deploytool surfaces DeployFailed carrying the project
    label. DEPLOY_WITH_DEPS is absent from the subprocess env so the
    Makefile's precheck-editable stays on its hard-fail branch.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=1, stderr=_EDITABLE_HARD_FAIL_STDERR)

    msgs = _capture_io(monkeypatch)
    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_WITH_DEPS", raising=False)

    args = _make_args(["bbsengine6.tui"], with_deps=False, editable=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")

    assert excinfo.value.label == "bbsengine6.tui"
    assert excinfo.value.rc == 1
    assert "DEPLOY_WITH_DEPS" not in captured["env"], (
        "DEPLOY_WITH_DEPS leaked into the subprocess env; the Makefile "
        "would switch to warn-and-proceed and the precheck would no "
        "longer catch the shadow at this layer."
    )
    assert captured["cmd"][:3] == [
        "make", "-C", f"{deploytool.lib.SOURCE_BASE}/bbsengine6",
    ]
    assert captured["cmd"][-1] == "deploy-tui"
    # The Makefile's stderr is surfaced to the operator via io.echo at
    # error level (lib.run_make_deploy:_run_subpostprocess error path).
    assert any("editable source:" in m for m in msgs), (
        "operator-facing breadcrumb from precheck-editable was not "
        "echoed; the silent-no-op would be back."
    )


# ---------------------------------------------------------------------------
# non-editable + --with-deps set → precheck warns, verify-install is the
# real correctness check
# ---------------------------------------------------------------------------


def test_shadow_install_caught_by_verify_install_when_with_deps_overrides(
    monkeypatch,
):
    """Editable install + non-editable branch + --with-deps: precheck-editable
    warns and proceeds; the post-install verify-install triple-check is the
    actual correctness contract. If it catches the shadow (pip show
    disagrees with the wheel's METADATA), the Makefile exits non-zero
    and deploytool surfaces DeployFailed.

    This is the load-bearing test: it pins the trailing `$(verify-install)`
    on `bbsengine6/py/src/Makefile:186-187`, the line that would have
    caught the original silent-no-op (bbsengine6/TODO.md:28-35) if it
    had been in place.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(
            returncode=1,
            stdout="WHEEL=/srv/repo/bbsengine6/bbsengine6-"
                   "0.0.1.dev20260830184512-py3-none-any.whl\n",
            stderr=_VERIFY_INSTALL_FAILED_STDERR,
        )

    msgs = _capture_io(monkeypatch)
    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)

    args = _make_args(["bbsengine6.tui"], with_deps=True, editable=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")

    assert excinfo.value.label == "bbsengine6.tui"
    assert excinfo.value.rc == 1
    assert captured["env"].get("DEPLOY_WITH_DEPS") == "1", (
        "DEPLOY_WITH_DEPS=1 must be in the subprocess env so the "
        "Makefile's precheck-editable switches to warn-and-proceed; "
        "without it, the precheck would hard-fail before the install "
        "even runs and verify-install would never get a chance to "
        "diagnose the shadow."
    )
    assert any("verify-install FAILED" in m for m in msgs), (
        "verify-install diagnostic was not surfaced; if this regression "
        "fires, the operator loses the precise diagnosis naming the "
        "editable-install cause."
    )
    assert any("expected METADATA" in m for m in msgs), (
        "verify-install's three-way diff (filename / METADATA / pip "
        "show) must reach the operator; without it the silent-no-op "
        "comes back with no breadcrumb."
    )


# ---------------------------------------------------------------------------
# non-editable + --with-deps set + no shadow → clean deploy
# ---------------------------------------------------------------------------


def test_shadow_install_warns_and_proceeds_with_with_deps(monkeypatch):
    """Editable install + non-editable branch + --with-deps, but verify-install
    triple-check agrees (clean wheel install): the deploy returns 0 and
    DEPLOY_WITH_DEPS=1 is plumbed. This is the success-path companion to
    test_shadow_install_caught_by_verify_install_when_with_deps_overrides
    and pins that --with-deps does not itself cause a failure when
    there's no actual shadow.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0, stdout=_CLEAN_DEPLOY_STDOUT)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)

    args = _make_args(["bbsengine6.tui"], with_deps=True, editable=False)
    rc = deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")

    assert rc == 0
    assert captured["env"].get("DEPLOY_WITH_DEPS") == "1"
    assert captured["cmd"][-1] == "deploy-tui"


# ---------------------------------------------------------------------------
# no editable install → no shadow → clean deploy, --with-deps unset
# ---------------------------------------------------------------------------


def test_no_shadow_install_passes_silently(monkeypatch):
    """Negative control: wheel install only (no editable), --with-deps
    unset. DEPLOY_WITH_DEPS is absent from the subprocess env (so a
    stray shell var can't flip the Makefile out of its default branch),
    the precheck has nothing to flag, verify-install agrees, the
    deploy returns 0.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0, stdout=_CLEAN_DEPLOY_STDOUT)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_WITH_DEPS", raising=False)

    args = _make_args(["bbsengine6.tui"], with_deps=False, editable=False)
    rc = deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")

    assert rc == 0
    assert "DEPLOY_WITH_DEPS" not in captured["env"], (
        "DEPLOY_WITH_DEPS leaked into the subprocess env under the "
        "default --with-deps=False path; the Makefile would switch to "
        "warn-and-proceed for no reason, defeating the "
        "strip-on-inherit contract documented in lib.py:454-471."
    )
    assert captured["cmd"][-1] == "deploy-tui"


# ---------------------------------------------------------------------------
# mistermcfeely: precheck-editable + verify-install + tui/prod split
#
# mistermcfeely is the project with explicit `tui` and `prod`
# sub-targets. The `tui` sub-target is operator-side (no sudo) and
# installs into the operator's active venv; the `prod` sub-target
# is the sudo umbrella (sysusers + tmpfiles + systemd + etc) and
# also installs the wheel into the operator's active venv. The PEP
# 660 editable-shadow precheck and the post-install verify-install
# check run from operator context (no sudo) and query the operator's
# venv via direct dist-info reads — see `mistermcfeely/Makefile`
# macros and `SPECS.md §5.1`.
#
# These tests pin the Makefile shape so a future commit can't drop
# the multi-package loop, the no-sudo dist-info reads, the
# `DEPLOY_WITH_DEPS` branching, or the `tui` / `prod` / `build`
# target wiring.
# ---------------------------------------------------------------------------

import os as _os


_MISTERMCFEELY_MAKEFILE = "/home/opencode/data/work/mistermcfeely/Makefile"


@pytest.fixture
def mistermcfeely_makefile():
    if not _os.path.exists(_MISTERMCFEELY_MAKEFILE):
        pytest.skip(f"{_MISTERMCFEELY_MAKEFILE} not present (sibling repo absent)")
    return _os.path.realpath(_MISTERMCFEELY_MAKEFILE)


def _read_text(path):
    return open(path).read()


def test_mistermcfeely_declares_wheel_packages(mistermcfeely_makefile):
    """mistermcfeely/Makefile declares `WHEEL_PACKAGES := bbsengine6 mistermcfeely`
    at the top so precheck-editable and verify-install iterate over
    every package whose wheel lands in $(OUTDIR). Without this
    variable, the macros have no list to loop over and the
    multi-package batch install is unchecked.
    """
    text = _read_text(mistermcfeely_makefile)
    assert "WHEEL_PACKAGES" in text, (
        "mistermcfeely/Makefile is missing WHEEL_PACKAGES. The "
        "precheck-editable and verify-install macros iterate over "
        "this list so a single macro covers the batch install "
        "(bbsengine6 wheel + mistermcfeely wheel). Add "
        "`WHEEL_PACKAGES := bbsengine6 mistermcfeely` to the "
        "variable block at the top of the Makefile."
    )
    assert "WHEEL_PACKAGES := bbsengine6 mistermcfeely" in text, (
        "WHEEL_PACKAGES is declared but doesn't list both "
        "bbsengine6 and mistermcfeely. The batch install lands "
        "both wheels into the operator's active venv, so both must "
        "be precheck'd and verify'd."
    )


def test_mistermcfeely_defines_outdir(mistermcfeely_makefile):
    """mistermcfeely/Makefile declares an `OUTDIR` (default `dist/`)
    so wheels land in a writable location. The default is the local
    project tree (`dist/`) so the operator doesn't need to be in the
    `repo` group to write wheels; override with OUTDIR= on the make
    command line or in the shell env to write to the cross-project
    /srv/repo/mistermcfeely/ location (used by bed/casino/zoid6/
    bbsengine6). The OUTDIR is what deploy-tui and the install-venv
    step consume via `ls -t $(OUTDIR)/*.whl`.
    """
    text = _read_text(mistermcfeely_makefile)
    # Accept the literal `dist/`, the cross-project
    # `/srv/repo/$(PROJECT)/`, the absolute `/srv/repo/mistermcfeely/`,
    # or any `OUTDIR ?= ...` override form.
    assert (
        "OUTDIR ?= dist/" in text
        or "OUTDIR = dist/" in text
        or "OUTDIR ?= /srv/repo/mistermcfeely/" in text
        or "OUTDIR = /srv/repo/mistermcfeely/" in text
        or "OUTDIR ?= /srv/repo/$(PROJECT)/" in text
        or "OUTDIR = /srv/repo/$(PROJECT)/" in text
    ), (
        "mistermcfeely/Makefile is missing an `OUTDIR` variable. "
        "Default is `dist/` (local project tree); override with "
        "OUTDIR=... to write to the cross-project /srv/repo/"
        "mistermcfeely/ location. install-venv and deploy-tui "
        "consume from $(OUTDIR) via `ls -t $(OUTDIR)/*.whl` after "
        "`make build` populates it."
    )


def test_mistermcfeely_defines_precheck_editable(mistermcfeely_makefile):
    """mistermcfeely/Makefile defines the precheck-editable macro via
    `define`/`endef` (recipe-time, so it can use shell-only
    constructs like `cat direct_url.json` and `$(PYTHON) -c ...`).
    """
    text = _read_text(mistermcfeely_makefile)
    assert "define precheck-editable" in text, (
        "mistermcfeely/Makefile is missing `define precheck-editable`. "
        "The PEP 660 editable-shadow precheck must run as a recipe-"
        "time macro so it can read dist-info/direct_url.json "
        "directly (PEP 610) without invoking pip show (which would "
        "need sudo)."
    )
    assert "endef" in text, "macro definition is missing the closing `endef`"


def test_mistermcfeely_defines_verify_install(mistermcfeely_makefile):
    """mistermcfeely/Makefile defines the verify-install macro via
    `define`/`endef`. Catches the silent-no-op case where
    `pip install <wheel>` exits 0 without replacing an existing
    install.
    """
    text = _read_text(mistermcfeely_makefile)
    assert "define verify-install" in text, (
        "mistermcfeely/Makefile is missing `define verify-install`. "
        "The post-install triple-check (filename / METADATA / "
        "dist-info Version) catches silent no-ops where pip "
        "reports success but didn't actually replace the prior "
        "install."
    )
    assert "endef" in text, "macro definition is missing the closing `endef`"


def test_mistermcfeely_macros_iterate_over_wheel_packages(mistermcfeely_makefile):
    """Both macros iterate over `$(WHEEL_PACKAGES)` so a single
    macro call covers the batch install. If a future commit
    hardcodes `bbsengine6` instead of looping, the multi-package
    contract is silently broken.
    """
    text = _read_text(mistermcfeely_makefile)
    precheck_section = text.split("define precheck-editable", 1)[1].split("endef", 1)[0]
    verify_section = text.split("define verify-install", 1)[1].split("endef", 1)[0]
    assert "for pkg in $(WHEEL_PACKAGES)" in precheck_section, (
        "precheck-editable does not iterate over $(WHEEL_PACKAGES). "
        "The batch install lands both bbsengine6 + mistermcfeely "
        "wheels; the precheck must check both."
    )
    assert "for pkg in $(WHEEL_PACKAGES)" in verify_section, (
        "verify-install does not iterate over $(WHEEL_PACKAGES). "
        "The batch install lands both bbsengine6 + mistermcfeely "
        "wheels; verify must check both."
    )


def test_mistermcfeely_macros_use_no_sudo_dist_info_reads(mistermcfeely_makefile):
    """The macros read dist-info directly via the operator's python,
    NOT via pip show, and NOT via sudo. This is the no-sudo contract
    that lets deploy-tui run from operator context and lets the
    install-venv precheck query the operator's active venv via
    direct file reads.
    """
    text = _read_text(mistermcfeely_makefile)
    precheck_section = text.split("define precheck-editable", 1)[1].split("endef", 1)[0]
    verify_section = text.split("define verify-install", 1)[1].split("endef", 1)[0]

    # Both macros resolve site-packages via sysconfig, not pip show.
    assert "sysconfig.get_paths" in precheck_section, (
        "precheck-editable does not resolve site-packages via "
        "sysconfig.get_paths(). Without sysconfig, the macro can't "
        "locate the venv's site-packages directory from operator "
        "context without invoking pip (which would need sudo)."
    )
    assert "sysconfig.get_paths" in verify_section, (
        "verify-install does not resolve site-packages via "
        "sysconfig.get_paths(). Without sysconfig, the macro can't "
        "locate the venv's dist-info directory from operator "
        "context without invoking pip (which would need sudo)."
    )

    # Both macros read dist-info directly (no pip show).
    assert "direct_url.json" in precheck_section, (
        "precheck-editable does not read direct_url.json. PEP 660 "
        "editable installs write `dir_info: {editable: true}` to "
        "direct_url.json; wheel installs do not. The grep on "
        "direct_url.json catches the editable case."
    )
    assert "dist-info" in verify_section, (
        "verify-install does not read dist-info. The post-install "
        "check compares the wheel's filename Version / METADATA "
        "Version against the dist-info's METADATA Version — the "
        "direct file read avoids pip show and runs without sudo."
    )

    # Neither macro should ever invoke sudo. The contract: precheck
    # and verify are operator-context; sudo is only used in the
    # FHS install chain (install-sysusers/install-tmpfiles/install-
    # systemd/install-etc), not in the precheck/verify macros
    # themselves.
    assert "sudo" not in precheck_section, (
        "precheck-editable contains a sudo invocation. The "
        "no-sudo contract is required for deploy-tui (which runs as "
        "the operator) and for the install-venv precheck (which "
        "queries the operator's venv via direct file reads)."
    )
    assert "sudo" not in verify_section, (
        "verify-install contains a sudo invocation. Same rationale."
    )


def test_mistermcfeely_precheck_respects_deploy_with_deps(mistermcfeely_makefile):
    """precheck-editable branches on DEPLOY_WITH_DEPS (literal-string
    `=1` match): hard-fail under default, warn-and-proceed under
    --with-deps. Without the branch, an editable install would
    either always silently no-op (wrong) or always hard-fail (also
    wrong).
    """
    text = _read_text(mistermcfeely_makefile)
    precheck_section = text.split("define precheck-editable", 1)[1].split("endef", 1)[0]
    assert 'if [ "$(DEPLOY_WITH_DEPS)" = "1" ]' in precheck_section, (
        "precheck-editable is missing the DEPLOY_WITH_DEPS branch. "
        "When deploytool --with-deps is set, the precheck must "
        "warn-and-proceed (the post-install verify-install becomes "
        "the correctness check). Without --with-deps, hard-fail."
    )
    assert "exit 1" in precheck_section, (
        "precheck-editable is missing the hard-fail exit. Under "
        "DEPLOY_WITH_DEPS unset, an editable install must abort the "
        "deploy rather than silently no-op."
    )


def test_mistermcfeely_defines_deploy_tui_target(mistermcfeely_makefile):
    """mistermcfeely/Makefile has a `deploy-tui` target (no sudo).
    Mirrors casino.tui's shape: precheck-editable, then either
    editable install from source or wheel install from $(OUTDIR),
    then verify-install.
    """
    text = _read_text(mistermcfeely_makefile)
    assert "deploy-tui:" in text, (
        "mistermcfeely/Makefile is missing the `deploy-tui` target. "
        "This is the operator-side install path (no sudo) called "
        "by `deploy mistermcfeely.tui`."
    )


def test_mistermcfeely_defines_deploy_prod_target(mistermcfeely_makefile):
    """mistermcfeely/Makefile has a `deploy-prod` target — sudo
    umbrella alias for the full install chain. Mirrors the
    bed/zoid6 `prod` pattern.
    """
    text = _read_text(mistermcfeely_makefile)
    assert "deploy-prod:" in text, (
        "mistermcfeely/Makefile is missing the `deploy-prod` target. "
        "This is the sudo umbrella install called by "
        "`deploy mistermcfeely.prod`."
    )


def test_mistermcfeely_deploy_tui_invokes_precheck_and_verify(mistermcfeely_makefile):
    """The deploy-tui recipe invokes precheck-editable at the top
    and verify-install after the wheel install. If a future commit
    drops either invocation, the silent-no-op returns.
    """
    text = _read_text(mistermcfeely_makefile)
    # Match `^deploy-tui:` (start-of-line target definition), not
    # the error string `deploy-tui: ...` inside the precheck-editable
    # macro body which contains a `deploy-tui:` substring.
    deploy_tui_section = text.split("\ndeploy-tui:", 1)[1].split("\n\n", 1)[0]
    assert "$(precheck-editable)" in deploy_tui_section, (
        "deploy-tui recipe does not invoke precheck-editable. "
        "Without the precheck, an editable install in the "
        "operator's active venv would silently shadow the wheel "
        "install (PEP 660 trap)."
    )
    assert "$(verify-install)" in deploy_tui_section \
        or "$(call verify-install" in deploy_tui_section, (
        "deploy-tui recipe does not invoke verify-install "
        "(directly or via $(call verify-install,...)). Without "
        "the post-install check, a silent-no-op install (wrong "
        "venv, orphaned dist-info, permission-denied mid-install) "
        "goes undetected."
    )


def test_mistermcfeely_install_venv_invokes_precheck_and_verify(mistermcfeely_makefile):
    """The install-venv recipe (the wheel-install step prod chains
    through, running against the operator's active venv) also
    invokes precheck-editable and verify-install. Both run as the
    operator with `$(OPERATOR_PYTHON)` (resolved from `$VIRTUAL_ENV`
    / `$(PYTHON)`) so they query the operator's active venv
    correctly without sudo.
    """
    text = _read_text(mistermcfeely_makefile)
    install_venv_section = text.split("\ninstall-venv:", 1)[1].split("\n\n", 1)[0]
    assert "$(precheck-editable)" in install_venv_section, (
        "install-venv recipe does not invoke precheck-editable. "
        "An editable install of bbsengine6 or mistermcfeely in the "
        "operator's active venv would silently shadow the wheel "
        "install."
    )
    assert "$(verify-install)" in install_venv_section \
        or "$(call verify-install" in install_venv_section, (
        "install-venv recipe does not invoke verify-install "
        "(directly or via $(call verify-install,...)). The pip "
        "install needs a post-check to catch silent no-ops "
        "(wrong venv, orphaned dist-info, permission-denied "
        "mid-install)."
    )


def test_mistermcfeely_deploy_prod_forwards_env_vars(mistermcfeely_makefile):
    """deploy-prod forwards DEPLOY_EDITABLE, DEPLOY_WITH_DEPS, and
    DEPLOY_UPGRADE to the install sub-make. Without forwarding,
    an operator running `deploy --with-deps mistermcfeely.prod`
    would see the precheck hard-fail instead of warn-and-proceed.
    """
    text = _read_text(mistermcfeely_makefile)
    deploy_prod_section = text.split("deploy-prod:", 1)[1].split("\n\n", 1)[0]
    assert "DEPLOY_EDITABLE=$(DEPLOY_EDITABLE)" in deploy_prod_section, (
        "deploy-prod does not forward DEPLOY_EDITABLE. Without "
        "this, an operator's `--editable` choice would silently "
        "no-op for `deploy mistermcfeely.prod`."
    )
    assert "DEPLOY_WITH_DEPS=$(DEPLOY_WITH_DEPS)" in deploy_prod_section, (
        "deploy-prod does not forward DEPLOY_WITH_DEPS. Without "
        "this, the precheck-editable hard-fail branch is always "
        "taken even under `deploy --with-deps mistermcfeely.prod`."
    )
    assert "DEPLOY_UPGRADE=$(DEPLOY_UPGRADE)" in deploy_prod_section, (
        "deploy-prod does not forward DEPLOY_UPGRADE. Without "
        "this, the operator's venv pip install would not honor "
        "the `--upgrade` / `--no-upgrade` choice."
    )


# ---------------------------------------------------------------------------
# deploytool TARGETS: mistermcfeely is registered
# ---------------------------------------------------------------------------


def test_deploytool_targets_includes_mistermcfeely_tui_prod():
    """deploytool/lib.py TARGETS includes 'mistermcfeely': ['tui', 'prod']
    so `deploy mistermcfeely.tui` and `deploy mistermcfeely.prod`
    resolve via the standard sub-target machinery. Bare
    `deploy mistermcfeely` becomes ambiguous (lists [tui, prod])
    matching the bed/zoid6 multi-sub pattern.
    """
    import importlib
    # Reload lib in case pytest re-orders fixtures vs. earlier tests.
    lib = importlib.reload(deploytool.lib)
    assert "mistermcfeely" in lib.TARGETS, (
        "deploytool/lib.py TARGETS is missing 'mistermcfeely'. "
        "Without this entry, bare `deploy mistermcfeely` falls "
        "through to the bare-base branch (no TARGETS) and runs the "
        "umbrella `make deploy` target — which has been removed "
        "in favor of the explicit tui/prod split."
    )
    assert lib.TARGETS["mistermcfeely"] == ["tui", "prod"], (
        f"deploytool/lib.py TARGETS['mistermcfeely'] = "
        f"{lib.TARGETS['mistermcfeely']!r}; expected ['tui', 'prod']. "
        f"Order matters: 'tui' is the operator-side default; "
        f"'prod' is the sudo umbrella install."
    )


# ---------------------------------------------------------------------------
# mistermcfeely: precheck-editable respects the no-sudo constraint
# even when called from install-venv (the operator-venv path).
# ---------------------------------------------------------------------------


def test_mistermcfeely_install_venv_uses_no_sudo_macros(mistermcfeely_makefile):
    """Even when chained from the prod-path install chain, the
    precheck-editable and verify-install invocations within
    install-venv must NOT be wrapped in sudo. They query the
    operator's active venv via direct file reads from operator
    context (the operator IS the venv owner).
    """
    text = _read_text(mistermcfeely_makefile)
    install_venv_section = text.split("install-venv:", 1)[1].split("\n\n", 1)[0]

    # Find the lines invoking precheck-editable and verify-install.
    precheck_lines = [
        line for line in install_venv_section.splitlines()
        if "$(precheck-editable)" in line
    ]
    verify_lines = [
        line for line in install_venv_section.splitlines()
        if "$(verify-install)" in line or "$(call verify-install" in line
    ]
    assert precheck_lines, "precheck-editable is not invoked from install-venv"
    assert verify_lines, "verify-install is not invoked from install-venv"
    for line in precheck_lines + verify_lines:
        assert "sudo" not in line, (
            f"install-venv invokes a macro with sudo: {line!r}. "
            f"The macros are designed to run from operator context "
            f"via direct dist-info reads; wrapping them in sudo "
            f"would either fail with permission-denied (the "
            f"operator's pip show under sudo sees root's site-"
            f"packages, not the operator venv's) or query the "
            f"wrong venv."
        )


# ---------------------------------------------------------------------------
# mistermcfeely: the operator-venv layout is the only layout. The
# shared-zoid6-venv model was reversed; this test pins the absence
# of any zoid6-owned venv plumbing so a future commit can't silently
# reintroduce the cross-project coupling.
# ---------------------------------------------------------------------------


def test_mistermcfeely_makefile_omits_zoid6_venv_paths(mistermcfeely_makefile):
    """mistermcfeely/Makefile no longer references the shared
    zoid6 venv (`/var/lib/zoid6/venv`), the `zoid6` user/group,
    or `sudo -u zoid6`. Both `deploy-tui` and `deploy-prod` install
    into the operator's active venv (`$(OPERATOR_VENV)`); the
    `VENV_LAYOUT['mistermcfeely']` registry entry in deploytool
    resolves to `VENV_USER` (the runtime operator-venv sentinel).
    """
    text = _read_text(mistermcfeely_makefile)
    forbidden = [
        ("VENV_DIR ?= /var/lib/zoid6/venv", "shared zoid6 venv path"),
        ("VENV_OWNER ?= zoid6", "shared zoid6 venv owner"),
        ("VENV_GROUP ?= zoid6", "shared zoid6 venv group"),
        ("VENV_SHARED ?= /var/lib/zoid6/venv", "shared zoid6 venv SHARED sentinel"),
        ("sudo -u zoid6", "shared-venv sudo switch"),
        ("sudo -u $(VENV_OWNER)", "shared-venv sudo switch (legacy)"),
        ("make -C ../zoid6", "cross-project make pointer"),
    ]
    for needle, what in forbidden:
        assert needle not in text, (
            f"mistermcfeely/Makefile contains {needle!r} ({what}). "
            f"mistermcfeely has been decoupled from the shared zoid6 "
            f"venv; both `deploy-tui` and `deploy-prod` install into "
            f"the operator's active venv (`$(OPERATOR_VENV)`). Drop "
            f"this reference."
        )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))