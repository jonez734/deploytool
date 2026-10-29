"""zoid6.venv: the staged-wheel venv route.

zoid6.wheels syncs the wheels into the account home (root). zoid6.venv installs them as the account.
The engine is installed by bbsengine6's venv sub, not prod. Guards the venv path, the sub names,
the dependency order, and that the zoid6 conditional table keeps its www edge.
"""

import pathlib

import pytest

import deploytool.lib as lib


def test_zoid6_venv_dir_is_the_account_home():
    assert lib.VENV_LAYOUT["zoid6"] == "/home/zoid6/venv"


def test_zoid6_declares_wheels_and_venv_subs():
    subs = lib.get_targets("zoid6")
    assert "wheels" in subs and "venv" in subs


def test_zoid6_venv_runs_after_wheels_and_engine_venv_not_prod():
    order = lib.resolve(["zoid6.venv"], with_deps=True)
    assert ("zoid6", "wheels") in order and ("zoid6", "venv") in order
    assert order.index(("zoid6", "wheels")) < order.index(("zoid6", "venv"))
    assert ("bbsengine6", "prod") not in order
    assert ("bbsengine6", "venv") in order


def test_wheels_and_venv_map_to_their_make_targets():
    assert lib.MAKE_TARGET_ALIASES[("zoid6", "wheels")] == "sync-wheels"
    assert lib.MAKE_TARGET_ALIASES[("zoid6", "venv")] == "install-wheels"


def test_zoid6_www_keeps_its_prod_edge():
    assert ("bbsengine6", "prod") in lib.resolve(["zoid6.www"], with_deps=True)


def test_shared_stays_unambiguous_with_the_new_subs():
    assert lib.resolve(["zoid6.shared"], with_deps=False) == [("zoid6", "shared")]


def test_zoid6_venv_runs_as_the_zoid6_account():
    """The account install runs as zoid6 (sudo -u zoid6), so install-wheels' own check passes."""
    assert lib.RUN_AS[("zoid6", "venv")] == "zoid6"


def _manifest(tmp_path, names):
    m = tmp_path / "zoid6-wheels.txt"
    m.write_text("# comment\n" + "\n".join(names) + "\n")
    return m


def _echoes(monkeypatch):
    out = []
    monkeypatch.setattr(lib.io, "echo", lambda msg, *a, **k: out.append(str(msg)))
    return out


def test_zoid6_wheels_runs_the_labelled_helper_first(monkeypatch, tmp_path):
    """The build is a helper run by deploy zoid6.wheels; it must be announced as one."""
    out = _echoes(monkeypatch)
    calls = []
    monkeypatch.setattr(lib, "_run_subprocess",
                        lambda cmd, **k: calls.append(cmd) or type("R", (), {"stdout": ""})())
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_DIST", str(tmp_path / "dist"))
    (tmp_path / "dist").mkdir()
    monkeypatch.setattr(lib, "ZOID6_MANIFEST", str(_manifest(tmp_path, [])))
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_INSTALLER", str(tmp_path / "dist" / "INSTALL.sh"))
    lib.run_zoid6_wheels(type("A", (), {"timeout": 5})())
    assert calls and calls[0][0] == "sh" and calls[0][1].endswith("build_zoid6_wheels.sh")
    assert any("helper:" in line and "build_zoid6_wheels.sh" in line for line in out)


def test_helper_is_labelled_as_deploy_run():
    text = (pathlib.Path(lib.ZOID6_BUILD_HELPER)).read_text()
    assert "HELPER" in text.splitlines()[1]
    assert "run by" in text.splitlines()[1] and "deploy zoid6.wheels" in text.splitlines()[1]


def test_zoid6_wheels_stops_before_copy_when_not_group_writable(monkeypatch, tmp_path):
    """Jam writes the account home through group zoid6; a non-writable target stops with the fix."""
    out = _echoes(monkeypatch)
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_DIST", str(dist))
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: False)
    monkeypatch.setattr(lib, "_run_subprocess", lambda cmd, **k: type("R", (), {"stdout": ""})())
    with pytest.raises(lib.DeployFailed) as ei:
        lib.run_zoid6_wheels(type("A", (), {"timeout": 5})())
    assert ei.value.label == "zoid6.wheels"
    assert "chmod g+rwx" in "\n".join(out)


def test_zoid6_venv_stops_when_venv_not_group_writable(monkeypatch, tmp_path):
    out = _echoes(monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    installer = tmp_path / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_INSTALLER", str(installer))
    monkeypatch.setattr(lib, "ZOID6_VENV", str(venv))
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: False)
    with pytest.raises(lib.DeployFailed) as ei:
        lib.run_zoid6_venv(type("A", (), {"timeout": 5})())
    assert ei.value.label == "zoid6.venv"
    assert "chmod -R g+rwX" in "\n".join(out)


def test_zoid6_venv_runs_the_installer_as_jam_with_dist_and_venv(monkeypatch, tmp_path):
    _echoes(monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    installer = tmp_path / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    seen = {}
    def fake(cmd, *, env, **k):
        seen["cmd"], seen["env"] = cmd, env
        return type("R", (), {"stdout": "bed 0.4\n"})()
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_INSTALLER", str(installer))
    monkeypatch.setattr(lib, "ZOID6_VENV", str(venv))
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_DIST", str(tmp_path / "dist"))
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: True)
    monkeypatch.setattr(lib, "_run_subprocess", fake)
    lib.run_zoid6_venv(type("A", (), {"timeout": 5})())
    assert seen["cmd"] == ["sh", str(installer)]
    assert seen["env"]["VENV"] == str(venv)
    assert seen["env"]["DIST"] == str(tmp_path / "dist")


def test_zoid6_venv_dry_run_does_not_abort(monkeypatch):
    out = _echoes(monkeypatch)
    args = type("A", (), {"dry_run": True})()
    assert lib.run_make_deploy(args, "zoid6", "venv") == 0
    assert "dry-run" in "\n".join(out)


def test_zoid6_wheels_dry_run_does_not_abort(monkeypatch):
    out = _echoes(monkeypatch)
    args = type("A", (), {"dry_run": True})()
    assert lib.run_make_deploy(args, "zoid6", "wheels") == 0
    assert "dry-run" in "\n".join(out)


def test_zoid6_steps_are_wired_in_run_make_deploy():
    import inspect
    src = inspect.getsource(lib.run_make_deploy)
    assert "run_zoid6_wheels" in src and "run_zoid6_venv" in src
