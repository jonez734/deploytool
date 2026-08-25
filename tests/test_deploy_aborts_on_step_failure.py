"""Regression tests: a failing deploy step aborts the chain.

Asserts that:

- `run_make_deploy` raises `deploytool.lib.DeployFailed(rc, label)` on
  any non-zero subprocess exit, timeout, command-not-found, or other
  OSError, and returns 0 on success. KeyboardInterrupt and SystemExit
  propagate (they are not swallowed).
- `run_verify` has the same contract and additionally skips silently
  when `bbsengine6` is not in the requested projects.
- `main.main()` catches `DeployFailed` once per call site, returns 1,
  and stops at the failing project. A failed verify step no longer
  reports `deploy complete`.
- Both functions run subprocesses with the documented hardening
  kwargs (`encoding="utf-8"`, `errors="replace"`, `timeout`, `start_new_session=True`).
- Both functions correctly populate the `env` dict passed to the
  subprocess (`--editable` set/clear, editable-var strip when not).
- The CLI parser exposes `--timeout` and rejects `--verbose`.
"""

import subprocess
import types
from argparse import Namespace

import pytest

import deploytool.lib
import deploytool.main


def _make_args(projects, *, verify=False, dry_run=False, editable=False, with_deps=False, timeout=None, **overrides):
    defaults = dict(
        projects=projects,
        host="merlin",
        dry_run=dry_run,
        verify=verify,
        editable=editable,
        with_deps=with_deps,
    )
    if timeout is not None:
        defaults["timeout"] = timeout
    defaults.update(overrides)
    return Namespace(**defaults)


def _completed(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# ---------------------------------------------------------------------------
# run_make_deploy — exception contract
# ---------------------------------------------------------------------------


def test_run_make_deploy_raises_on_nonzero_rc(monkeypatch):
    """Non-zero rc from subprocess raises DeployFailed with the rc and label."""
    monkeypatch.setattr(
        deploytool.lib.subprocess, "run",
        lambda *a, **kw: _completed(returncode=2, stderr="boom"),
    )
    args = _make_args(["bbsengine6.www"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert excinfo.value.rc == 2
    assert excinfo.value.label == "bbsengine6.www"


def test_run_make_deploy_returns_zero_on_success(monkeypatch):
    """Successful make returns 0 and does not raise."""
    monkeypatch.setattr(
        deploytool.lib.subprocess, "run",
        lambda *a, **kw: _completed(returncode=0, stdout="built wheels"),
    )
    args = _make_args(["bbsengine6.www"], dry_run=False)
    assert deploytool.lib.run_make_deploy(args, "bbsengine6", "www") == 0


def test_run_make_deploy_dry_run_invokes_make_with_dry_run_flag(monkeypatch):
    """Dry-run invokes subprocess with `--dry-run` appended to cmd and DEPLOY_DRY_RUN=1 in env."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6.www"], dry_run=True)
    assert deploytool.lib.run_make_deploy(args, "bbsengine6", "www") == 0

    assert captured["cmd"][-1] == "--dry-run"
    assert captured["cmd"][:3] == ["make", "-C", f"{deploytool.lib.SOURCE_BASE}/bbsengine6"]
    assert captured["cmd"][3] == "deploy-www"
    assert captured["env"].get("DEPLOY_DRY_RUN") == "1"


def test_run_make_deploy_dry_run_strips_env_var_when_not_set(monkeypatch):
    """When --dry-run is NOT passed, DEPLOY_DRY_RUN is stripped from env."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_DRY_RUN", raising=False)
    monkeypatch.setenv("DEPLOY_DRY_RUN", "1")
    monkeypatch.setenv("PATH", "/usr/bin")  # always present

    args = _make_args(["bbsengine6.www"], dry_run=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert "DEPLOY_DRY_RUN" not in captured["env"]
    assert captured["env"]["PATH"] == "/usr/bin"


def test_run_make_deploy_dry_run_aborts_on_nonzero_rc(monkeypatch):
    """A non-zero `make --dry-run` rc still raises DeployFailed."""
    monkeypatch.setattr(
        deploytool.lib.subprocess, "run",
        lambda *a, **kw: _completed(returncode=2, stderr="dry-run broken"),
    )
    args = _make_args(["bbsengine6.www"], dry_run=True)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert excinfo.value.rc == 2
    assert excinfo.value.label == "bbsengine6.www"


def test_run_make_deploy_raises_on_timeout(monkeypatch):
    """subprocess.TimeoutExpired becomes DeployFailed(rc=-1, label)."""
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="make", timeout=600)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6.www"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert excinfo.value.rc == -1
    assert excinfo.value.label == "bbsengine6.www"
    assert isinstance(excinfo.value.__cause__, subprocess.TimeoutExpired)


def test_run_make_deploy_raises_on_command_not_found(monkeypatch):
    """FileNotFoundError (e.g. make missing) becomes DeployFailed(rc=-1)."""
    def boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory", "make")

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6.www"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert excinfo.value.rc == -1
    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_run_make_deploy_raises_on_oserror(monkeypatch):
    """Generic OSError becomes DeployFailed(rc=-1)."""
    def boom(*a, **kw):
        raise OSError("disk on fire")

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6.www"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert excinfo.value.rc == -1
    assert isinstance(excinfo.value.__cause__, OSError)


def test_run_make_deploy_propagates_keyboard_interrupt(monkeypatch):
    """KeyboardInterrupt is NOT caught — the user can Ctrl-C."""
    def boom(*a, **kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6.www"], dry_run=False)
    with pytest.raises(KeyboardInterrupt):
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")


def test_run_make_deploy_propagates_system_exit(monkeypatch):
    """SystemExit is NOT caught."""
    def boom(*a, **kw):
        raise SystemExit(2)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6.www"], dry_run=False)
    with pytest.raises(SystemExit):
        deploytool.lib.run_make_deploy(args, "bbsengine6", "www")


# ---------------------------------------------------------------------------
# run_make_deploy — hardening kwargs
# ---------------------------------------------------------------------------


def test_run_make_deploy_passes_hardening_kwargs(monkeypatch):
    """subprocess.run is called with the documented hardening kwargs."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured.update(kwargs)
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6.www"], dry_run=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "www")

    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["check"] is False
    assert captured["start_new_session"] is True
    assert captured["capture_output"] is True
    assert captured["text"] is True
    assert captured["timeout"] == deploytool.lib.DEFAULT_TIMEOUT_SECONDS


def test_run_make_deploy_uses_timeout_from_args(monkeypatch):
    """args.timeout overrides the default."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6.www"], dry_run=False, timeout=42)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert captured["timeout"] == 42


# ---------------------------------------------------------------------------
# run_make_deploy — env handling
# ---------------------------------------------------------------------------


def test_run_make_deploy_strips_editable_vars_when_not_editable(monkeypatch, tmp_path):
    """When --editable is NOT passed, DEPLOY_EDITABLE/EDITABLE/DEV are stripped."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_EDITABLE", raising=False)
    monkeypatch.delenv("EDITABLE", raising=False)
    monkeypatch.delenv("DEV", raising=False)
    monkeypatch.setenv("DEPLOY_EDITABLE", "1")
    monkeypatch.setenv("EDITABLE", "1")
    monkeypatch.setenv("DEV", "1")
    monkeypatch.setenv("PATH", "/usr/bin")  # always present

    args = _make_args(["bbsengine6.www"], dry_run=False, editable=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert "DEPLOY_EDITABLE" not in captured["env"]
    assert "EDITABLE" not in captured["env"]
    assert "DEV" not in captured["env"]
    assert captured["env"]["PATH"] == "/usr/bin"


def test_run_make_deploy_sets_deploy_editable_when_editable(monkeypatch):
    """When --editable is passed, DEPLOY_EDITABLE=1 is set in env."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_EDITABLE", raising=False)
    monkeypatch.setenv("EDITABLE", "1")

    args = _make_args(["bbsengine6.www"], dry_run=False, editable=True)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "www")
    assert captured["env"]["DEPLOY_EDITABLE"] == "1"


# ---------------------------------------------------------------------------
# run_verify — exception contract
# ---------------------------------------------------------------------------


def test_run_verify_raises_on_nonzero_rc(monkeypatch):
    """Non-zero rc from the verify subprocess raises DeployFailed."""
    monkeypatch.setattr(
        deploytool.lib.subprocess, "run",
        lambda *a, **kw: _completed(returncode=3, stderr="render broken"),
    )
    args = _make_args(["bbsengine6"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_verify(args, ["bbsengine6"])
    assert excinfo.value.rc == 3
    assert excinfo.value.label == "verify.bbsengine6"


def test_run_verify_returns_zero_on_success(monkeypatch):
    """Successful verify returns 0 and does not raise."""
    monkeypatch.setattr(
        deploytool.lib.subprocess, "run",
        lambda *a, **kw: _completed(returncode=0),
    )
    args = _make_args(["bbsengine6"], dry_run=False)
    assert deploytool.lib.run_verify(args, ["bbsengine6"]) == 0


def test_run_verify_skips_when_bbsengine6_not_in_projects(monkeypatch):
    """verify does nothing and does not invoke subprocess when bbsengine6 absent."""
    def boom(*a, **kw):
        raise AssertionError("subprocess.run must not be called")

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bed", "zoid6"], dry_run=False)
    assert deploytool.lib.run_verify(args, ["bed", "zoid6"]) == 0


def test_run_verify_dry_run_does_not_invoke_subprocess(monkeypatch):
    """Dry-run prints the command and returns 0 without invoking subprocess."""
    def boom(*a, **kw):
        raise AssertionError("subprocess.run must not be called in dry-run")

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6"], dry_run=True)
    assert deploytool.lib.run_verify(args, ["bbsengine6"]) == 0


def test_run_verify_raises_on_timeout(monkeypatch):
    """subprocess.TimeoutExpired in verify becomes DeployFailed(rc=-1)."""
    def boom(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="php", timeout=600)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_verify(args, ["bbsengine6"])
    assert excinfo.value.rc == -1
    assert excinfo.value.label == "verify.bbsengine6"


def test_run_verify_raises_on_command_not_found(monkeypatch):
    """FileNotFoundError in verify becomes DeployFailed(rc=-1)."""
    def boom(*a, **kw):
        raise FileNotFoundError(2, "No such file or directory", "php")

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6"], dry_run=False)
    with pytest.raises(deploytool.lib.DeployFailed) as excinfo:
        deploytool.lib.run_verify(args, ["bbsengine6"])
    assert excinfo.value.rc == -1


def test_run_verify_propagates_keyboard_interrupt(monkeypatch):
    """KeyboardInterrupt in verify propagates (not caught)."""
    def boom(*a, **kw):
        raise KeyboardInterrupt()

    monkeypatch.setattr(deploytool.lib.subprocess, "run", boom)
    args = _make_args(["bbsengine6"], dry_run=False)
    with pytest.raises(KeyboardInterrupt):
        deploytool.lib.run_verify(args, ["bbsengine6"])


def test_run_verify_passes_cwd_to_subprocess(monkeypatch):
    """verify passes cwd=... so php runs in the bbsengine6/php dir."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6"], dry_run=False)
    deploytool.lib.run_verify(args, ["bbsengine6"])
    assert captured["cwd"] == f"{deploytool.lib.SOURCE_BASE}/bbsengine6/php"


# ---------------------------------------------------------------------------
# main() — abort propagation
# ---------------------------------------------------------------------------


def test_main_aborts_on_make_failed(monkeypatch):
    """main() returns 1 and stops at the failing project."""
    call_log = []

    def fake_run_make_deploy(args, project, sub):
        call_log.append((project, sub))
        raise deploytool.lib.DeployFailed(7, f"{project}.{sub}" if sub else project)

    monkeypatch.setattr(deploytool.lib, "run_make_deploy", fake_run_make_deploy)
    args = _make_args(["bbsengine6.tui", "bed.tui"])
    assert deploytool.main.main(args) == 1
    assert call_log == [("bbsengine6", "tui")]


def test_main_aborts_on_verify_failed(monkeypatch):
    """main() returns 1 when verify raises DeployFailed."""
    monkeypatch.setattr(
        deploytool.lib, "run_make_deploy",
        lambda args, project, sub: 0,
    )

    def fake_run_verify(args, projects):
        raise deploytool.lib.DeployFailed(3, "verify.bbsengine6")

    monkeypatch.setattr(deploytool.lib, "run_verify", fake_run_verify)
    args = _make_args(["bbsengine6.www"], verify=True)
    assert deploytool.main.main(args) == 1


def test_main_completes_when_verify_passes(monkeypatch):
    """main() returns 0 when the chain and verify both succeed."""
    monkeypatch.setattr(
        deploytool.lib, "run_make_deploy",
        lambda args, project, sub: 0,
    )
    monkeypatch.setattr(deploytool.lib, "run_verify", lambda args, projects: 0)
    args = _make_args(["bbsengine6.www"], verify=True)
    assert deploytool.main.main(args) == 0


def test_main_skips_verify_when_not_requested(monkeypatch):
    """main() does not call run_verify when --verify is not set."""
    def boom(args, projects):
        raise AssertionError("run_verify must not be called")

    monkeypatch.setattr(deploytool.lib, "run_make_deploy", lambda a, p, s: 0)
    monkeypatch.setattr(deploytool.lib, "run_verify", boom)
    args = _make_args(["bbsengine6.www"], verify=False)
    assert deploytool.main.main(args) == 0


# ---------------------------------------------------------------------------
# CLI parser — --timeout and --verbose
# ---------------------------------------------------------------------------


def test_buildargs_default_timeout_is_default_constant():
    """Without --timeout, args.timeout == DEFAULT_TIMEOUT_SECONDS."""
    args = deploytool.lib.buildargs().parse_args(["bbsengine6"])
    assert args.timeout == deploytool.lib.DEFAULT_TIMEOUT_SECONDS


def test_buildargs_timeout_override():
    """--timeout N sets args.timeout == N."""
    args = deploytool.lib.buildargs().parse_args(["--timeout", "30", "bbsengine6"])
    assert args.timeout == 30


def test_buildargs_rejects_verbose_flag():
    """--verbose was removed; argparse rejects unknown args."""
    with pytest.raises(SystemExit):
        deploytool.lib.buildargs().parse_args(["--verbose", "bbsengine6"])


# ---------------------------------------------------------------------------
# DeployFailed exception class
# ---------------------------------------------------------------------------


def test_deploy_failed_carries_rc_and_label():
    """DeployFailed carries rc and label as attributes and a str message."""
    exc = deploytool.lib.DeployFailed(7, "bbsengine6.tui")
    assert exc.rc == 7
    assert exc.label == "bbsengine6.tui"
    assert "bbsengine6.tui" in str(exc)
    assert "7" in str(exc)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
