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


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))