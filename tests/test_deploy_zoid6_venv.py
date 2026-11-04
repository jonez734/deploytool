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


def test_zoid6_wheels_runs_the_labelled_helper_first(monkeypatch, tmp_path, instance_settings):
    """The build is a helper run by deploy zoid6.wheels; it must be announced as one."""
    out = _echoes(monkeypatch)
    calls = []
    monkeypatch.setattr(lib, "_run_subprocess",
                        lambda cmd, **k: calls.append(cmd) or type("R", (), {"stdout": ""})())
    (tmp_path / "dist").mkdir()
    instance_settings("zoid6", account_dist=str(tmp_path / "dist"),
                      manifest=str(_manifest(tmp_path, [])),
                      installer=str(tmp_path / "dist" / "INSTALL.sh"))
    lib.run_zoid6_wheels(type("A", (), {"timeout": 5})())
    assert calls and calls[0][0] == "sh" and calls[0][1].endswith("build_zoid6_wheels.sh")
    assert any("helper:" in line and "build_zoid6_wheels.sh" in line for line in out)


def test_helper_is_labelled_as_deploy_run():
    text = (pathlib.Path(lib._instance_settings("zoid6")["build_helper"])).read_text()
    assert "HELPER" in text.splitlines()[1]
    assert "run by" in text.splitlines()[1] and "deploy zoid6.wheels" in text.splitlines()[1]


def test_zoid6_wheels_stops_before_copy_when_not_group_writable(monkeypatch, tmp_path, instance_settings):
    """Jam writes the account home through group zoid6; a non-writable target stops with the fix."""
    out = _echoes(monkeypatch)
    dist = tmp_path / "dist"
    dist.mkdir()
    instance_settings("zoid6", account_dist=str(dist))
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: False)
    monkeypatch.setattr(lib, "_run_subprocess", lambda cmd, **k: type("R", (), {"stdout": ""})())
    with pytest.raises(lib.DeployFailed) as ei:
        lib.run_zoid6_wheels(type("A", (), {"timeout": 5})())
    assert ei.value.label == "zoid6.wheels"
    assert "chmod g+rwx" in "\n".join(out)


def test_zoid6_venv_stops_when_venv_not_group_writable(monkeypatch, tmp_path, instance_settings):
    out = _echoes(monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    installer = tmp_path / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    instance_settings("zoid6", installer=str(installer), venv=str(venv))
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: False)
    with pytest.raises(lib.DeployFailed) as ei:
        lib.run_zoid6_venv(type("A", (), {"timeout": 5})())
    assert ei.value.label == "zoid6.venv"
    assert "chmod -R g+rwX" in "\n".join(out)


def _bin_not_writable(monkeypatch, bindir):
    """Make only the venv's bin/ unwritable; the venv itself reports writable."""
    real = lib._writable_by_me
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: real(path) and path != str(bindir))


def test_zoid6_venv_stops_before_installer_when_bin_not_writable(monkeypatch, tmp_path, instance_settings):
    out = _echoes(monkeypatch)
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    installer = tmp_path / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    instance_settings("zoid6", installer=str(installer), venv=str(venv))
    _bin_not_writable(monkeypatch, venv / "bin")
    ran = []
    monkeypatch.setattr(lib, "_run_subprocess", lambda cmd, **k: ran.append(cmd))
    with pytest.raises(lib.DeployFailed) as ei:
        lib.run_zoid6_venv(type("A", (), {"timeout": 5})())
    assert ei.value.label == "zoid6.venv"
    assert ran == []


def test_bin_hint_is_built_from_the_registry(monkeypatch, tmp_path, instance_settings):
    out = _echoes(monkeypatch)
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    installer = tmp_path / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    instance_settings("zoid6", installer=str(installer), venv=str(venv), account="zoid6")
    _bin_not_writable(monkeypatch, venv / "bin")
    with pytest.raises(lib.DeployFailed):
        lib.run_zoid6_venv(type("A", (), {"timeout": 5})())
    text = "\n".join(out)
    assert f"sudo -u zoid6 {venv}/bin/deploy zoid6.venv --prefix={venv}" in text


def test_bin_hint_uses_the_second_instances_account_and_paths(tmp_path, monkeypatch):
    out = _echoes(monkeypatch)
    venv = tmp_path / "other-venv"
    (venv / "bin").mkdir(parents=True)
    dist = tmp_path / "dist"
    dist.mkdir()
    installer = dist / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    manifest = tmp_path / "other-wheels.txt"
    manifest.write_text("")
    settings = {
        "account": "othered", "group": "othered", "account_dist": str(dist), "venv": str(venv),
        "installer": str(installer), "installer_src": str(installer), "build_helper": str(installer),
        "stage": str(tmp_path), "manifest": str(manifest),
    }
    monkeypatch.setattr(lib, "_instance_settings", lambda n: dict(settings) if n == "othered" else None)
    _bin_not_writable(monkeypatch, venv / "bin")
    with pytest.raises(lib.DeployFailed):
        lib.run_bed_instance_venv("othered", type("A", (), {"timeout": 5})())
    text = "\n".join(out)
    assert f"sudo -u othered {venv}/bin/deploy othered.venv --prefix={venv}" in text
    assert "zoid6" not in text


def test_zoid6_venv_runs_the_installer_as_jam_with_dist_and_venv(monkeypatch, tmp_path, instance_settings):
    _echoes(monkeypatch)
    venv = tmp_path / "venv"
    venv.mkdir()
    installer = tmp_path / "INSTALL.sh"
    installer.write_text("#!/bin/sh\n")
    seen = {}
    def fake(cmd, **k):
        seen["cmd"] = cmd
        return type("R", (), {"stdout": "bed 0.4\n"})()
    instance_settings("zoid6", installer=str(installer), venv=str(venv), account_dist=str(tmp_path / "dist"))
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: True)
    monkeypatch.setattr(lib, "_run_subprocess", fake)
    monkeypatch.setattr(lib, "_manifest_wheels", lambda path: ["zoid6-0.5.0-py3-none-any.whl"])
    lib.run_zoid6_venv(type("A", (), {"timeout": 5})())
    # The shared installer runs pip into zoid6's venv from its dist directory, not the account script.
    assert seen["cmd"][:4] == [f"{venv}/bin/python", "-m", "pip", "install"]
    assert seen["cmd"][-1] == f"{tmp_path / 'dist'}/zoid6-0.5.0-py3-none-any.whl"
    assert str(installer) not in seen["cmd"]


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
    """run_make_deploy routes bed-instance subs through the generic functions, which zoid6 uses."""
    import inspect
    src = inspect.getsource(lib.run_make_deploy)
    assert "_instance_settings" in src or "_bed_instance_names" in src
    assert "run_bed_instance_wheels" in src and "run_bed_instance_venv" in src
    assert "zoid6" in lib._bed_instance_names()


def test_stage_file_replaces_without_copying_metadata(tmp_path, monkeypatch):
    """Staging must rename over the target, not copy2: copy2 fails on account-owned files (EPERM)."""
    src = tmp_path / "src.whl"
    src.write_bytes(b"new")
    dst = tmp_path / "dst.whl"
    dst.write_bytes(b"old")
    def no_copy2(*a, **k):
        raise PermissionError("copy2 touches metadata; must not be used")
    monkeypatch.setattr(lib.shutil, "copy2", no_copy2)
    lib._stage_file(str(src), str(dst), 0o644)
    assert dst.read_bytes() == b"new"
    assert (dst.stat().st_mode & 0o777) == 0o644
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())


def test_zoid6_staging_uses_stage_file_not_copy2():
    import inspect
    src = inspect.getsource(lib.run_bed_instance_wheels)
    assert "_stage_file(" in src and "copy2" not in src
