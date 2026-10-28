"""zoid6.venv: the staged-wheel venv route.

zoid6.wheels syncs the wheels into the account home (root). zoid6.venv installs them as the account.
The engine is installed by bbsengine6's venv sub, not prod. Guards the venv path, the sub names,
the dependency order, and that the zoid6 conditional table keeps its www edge.
"""

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


def test_preflight_names_the_sync_when_wheels_are_missing(tmp_path, monkeypatch):
    import pytest
    out = _echoes(monkeypatch)
    names = ["bed-0.4.0.dev1-py3-none-any.whl"]
    monkeypatch.setattr(lib, "ZOID6_MANIFEST", str(_manifest(tmp_path, names)))
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_DIST", str(tmp_path / "empty"))
    with pytest.raises(lib.DeployFailed) as ei:
        lib.preflight_zoid6_venv(object())
    assert ei.value.rc == 2
    text = "\n".join(out)
    assert "sudo sh" in text and "sync-zoid6-wheels.sh" in text


def test_preflight_names_the_account_install_when_synced(tmp_path, monkeypatch):
    out = _echoes(monkeypatch)
    names = ["bed-0.4.0.dev1-py3-none-any.whl"]
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / names[0]).write_bytes(b"")
    monkeypatch.setattr(lib, "ZOID6_MANIFEST", str(_manifest(tmp_path, names)))
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_DIST", str(dist))
    lib.preflight_zoid6_venv(object())  # returns normally
    assert f"sudo -u zoid6 sh {lib.ZOID6_ACCOUNT_INSTALLER}" in "\n".join(out)


def test_zoid6_venv_dry_run_does_not_abort(monkeypatch):
    out = _echoes(monkeypatch)
    monkeypatch.setattr(lib, "ZOID6_MANIFEST", "/nonexistent/manifest")
    args = type("A", (), {"dry_run": True})()
    assert lib.run_make_deploy(args, "zoid6", "venv") == 0
    assert "dry-run" in "\n".join(out)


def test_zoid6_venv_is_preflighted_not_the_repo_make_target():
    import inspect
    src = inspect.getsource(lib.run_make_deploy)
    assert '("zoid6", "venv")' in src and "preflight_zoid6_venv" in src


def test_zoid6_wheels_preflight_names_the_root_sync_when_not_synced(tmp_path, monkeypatch):
    out = _echoes(monkeypatch)
    monkeypatch.setattr(lib, "ZOID6_MANIFEST", str(_manifest(tmp_path, ["bed-0.4.0.dev1-py3-none-any.whl"])))
    monkeypatch.setattr(lib, "ZOID6_ACCOUNT_DIST", str(tmp_path / "empty"))
    import pytest
    with pytest.raises(lib.DeployFailed) as ei:
        lib.preflight_zoid6_wheels(object())
    assert ei.value.label == "zoid6.wheels"
    assert "sudo sh" in "\n".join(out)


def test_zoid6_wheels_is_preflighted_not_the_root_make_target(monkeypatch):
    import inspect
    src = inspect.getsource(lib.run_make_deploy)
    assert '("zoid6", "wheels")' in src and "preflight_zoid6_wheels" in src


def test_zoid6_wheels_dry_run_does_not_abort(monkeypatch):
    out = _echoes(monkeypatch)
    args = type("A", (), {"dry_run": True})()
    assert lib.run_make_deploy(args, "zoid6", "wheels") == 0
    assert "dry-run" in "\n".join(out)
