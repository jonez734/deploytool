"""A venv install stops before make when the target bin/ is not writable by the deploy user.

pip replaces console-script launchers in <prefix>/bin. When another account owns that directory,
the install fails partway through pip. The guard checks bin/ first and prints the owning account's
command. Nothing in the guard names an account.
"""

import importlib
import types

import pytest

lib = importlib.import_module("deploytool.lib")


def _args(**kw):
    base = dict(dry_run=False, prefix=None, editable=False, with_deps=False, upgrade=True, timeout=5)
    base.update(kw)
    return types.SimpleNamespace(**base)


@pytest.fixture
def ran(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(lib, "_run_subprocess", fake_run)
    return calls


@pytest.fixture
def echoes(monkeypatch):
    out = []
    monkeypatch.setattr(lib.io, "echo", lambda text="", *a, **k: out.append(str(text)))
    return out


def _venv_with_bin(tmp_path, writable):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin").chmod(0o755 if writable else 0o555)
    return venv


@pytest.mark.unit
def test_stops_before_make_when_bin_is_not_writable(tmp_path, monkeypatch, ran, echoes):
    venv = _venv_with_bin(tmp_path, writable=False)
    monkeypatch.setattr(lib, "_writable_by_me", lambda p: p != str(venv / "bin"))
    with pytest.raises(lib.DeployFailed) as ei:
        lib.run_make_deploy(_args(prefix=str(venv)), "bbsengine6", "venv")
    assert ei.value.rc == 2
    assert ran == [], "make must not run when bin/ is not writable"


@pytest.mark.unit
def test_printed_fix_is_the_owner_command_built_from_the_prefix(tmp_path, monkeypatch, ran, echoes):
    venv = _venv_with_bin(tmp_path, writable=False)
    monkeypatch.setattr(lib, "_writable_by_me", lambda p: p != str(venv / "bin"))
    with pytest.raises(lib.DeployFailed):
        lib.run_make_deploy(_args(prefix=str(venv)), "bbsengine6", "venv")
    text = "\n".join(echoes)
    assert f"--prefix={venv}" in text
    assert f"{venv}/bin/deploy bbsengine6.venv" in text
    assert "sudo -u " in text


@pytest.mark.unit
def test_runs_make_when_bin_is_writable(tmp_path, monkeypatch, ran, echoes):
    venv = _venv_with_bin(tmp_path, writable=True)
    monkeypatch.setattr(lib, "_writable_by_me", lambda p: True)
    lib.run_make_deploy(_args(prefix=str(venv)), "bbsengine6", "venv")
    assert ran, "make should run when bin/ is writable"


@pytest.mark.unit
def test_dry_run_does_not_trip_the_guard(tmp_path, monkeypatch, ran, echoes):
    venv = _venv_with_bin(tmp_path, writable=False)
    monkeypatch.setattr(lib, "_writable_by_me", lambda p: False)
    # A dry run returns without raising; the guard does not run for it.
    assert lib.run_make_deploy(_args(prefix=str(venv), dry_run=True), "bbsengine6", "venv") == 0


@pytest.mark.unit
def test_non_venv_subs_are_not_checked(tmp_path, monkeypatch, ran, echoes):
    venv = _venv_with_bin(tmp_path, writable=False)
    monkeypatch.setattr(lib, "_writable_by_me", lambda p: False)
    lib.run_make_deploy(_args(prefix=str(venv)), "bbsengine6", "tui")
    assert ran, "a non-venv sub must not be stopped by the venv guard"
