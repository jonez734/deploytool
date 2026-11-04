"""deploy --fill-wheelhouse INSTANCE: the CLI option, its checks, and its routing.

The download itself is stubbed; these tests cover the decisions around it.
"""

import importlib
import types

import pytest

from deploytool import lib

deploy_main = importlib.import_module("deploytool.main")


pytestmark = pytest.mark.unit


def _args(**kw):
    base = dict(projects=[], fill_wheelhouse=None, platform=None, with_deps=False, verify=False,
                dry_run=False, timeout=5, debug=False)
    base.update(kw)
    return types.SimpleNamespace(**base)


def _echoes(monkeypatch):
    out = []
    monkeypatch.setattr(lib.io, "echo", lambda text="", **kw: out.append(str(text)))
    return out


def test_buildargs_accepts_fill_without_projects():
    args = lib.buildargs().parse_args(["--fill-wheelhouse", "zoid6"])
    assert args.fill_wheelhouse == "zoid6"
    assert args.projects == []


def test_buildargs_accepts_platform_override():
    args = lib.buildargs().parse_args(["--fill-wheelhouse", "zoid6", "--platform", "manylinux_2_28_aarch64"])
    assert args.platform == "manylinux_2_28_aarch64"


def test_no_projects_and_no_fill_is_an_error(monkeypatch):
    out = _echoes(monkeypatch)
    assert deploy_main.main(_args(), argv=[]) == 2
    assert any("name a project" in t for t in out)


def test_fill_routes_to_the_fill_function(monkeypatch):
    _echoes(monkeypatch)
    seen = []
    monkeypatch.setattr(lib, "run_fill_wheelhouse", lambda name, args: seen.append(name) or 0)
    assert deploy_main.main(_args(fill_wheelhouse="zoid6"), argv=[]) == 0
    assert seen == ["zoid6"]


def test_fill_refuses_an_instance_without_a_wheelhouse(monkeypatch):
    settings = {"wheelhouse": None, "manifest": "/m", "stage": "/s"}
    monkeypatch.setattr(lib, "_instance_settings", lambda name: settings)
    with pytest.raises(ValueError, match="no wheelhouse directory"):
        lib.run_fill_wheelhouse("zoid6", _args())


def test_fill_refuses_when_internal_wheels_are_not_staged(monkeypatch, tmp_path):
    settings = {"wheelhouse": str(tmp_path / "wh"), "manifest": str(tmp_path / "m"), "stage": str(tmp_path)}
    (tmp_path / "m").write_text("bed-1-py3-none-any.whl\n")
    monkeypatch.setattr(lib, "_instance_settings", lambda name: settings)
    with pytest.raises(FileNotFoundError, match="not staged"):
        lib.run_fill_wheelhouse("zoid6", _args())


def test_fill_uses_the_default_platform_and_checks_completeness(monkeypatch, tmp_path):
    _echoes(monkeypatch)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "bed-1-py3-none-any.whl").write_bytes(b"x")
    (tmp_path / "m").write_text("bed-1-py3-none-any.whl\n")
    settings = {"wheelhouse": str(tmp_path / "wh"), "manifest": str(tmp_path / "m"), "stage": str(stage)}
    monkeypatch.setattr(lib, "_instance_settings", lambda name: settings)
    seen = {}

    from deploytool import wheelhouse

    def fake_fill(paths, dest, *, platform, python_version="3.12", timeout=None):
        seen["platform"] = platform
        return {"files": [], "requirements": []}

    monkeypatch.setattr(wheelhouse, "fill", fake_fill)
    monkeypatch.setattr(wheelhouse, "check", lambda dest: [])
    assert lib.run_fill_wheelhouse("zoid6", _args()) == 0
    assert seen["platform"] == wheelhouse.DEFAULT_PLATFORM


def test_an_incomplete_wheelhouse_fails_the_fill(monkeypatch, tmp_path):
    _echoes(monkeypatch)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "bed-1-py3-none-any.whl").write_bytes(b"x")
    (tmp_path / "m").write_text("bed-1-py3-none-any.whl\n")
    settings = {"wheelhouse": str(tmp_path / "wh"), "manifest": str(tmp_path / "m"), "stage": str(stage)}
    monkeypatch.setattr(lib, "_instance_settings", lambda name: settings)

    from deploytool import wheelhouse

    monkeypatch.setattr(wheelhouse, "fill", lambda *a, **k: {"files": [], "requirements": []})
    monkeypatch.setattr(wheelhouse, "check", lambda dest: ["pillow-12.0.whl"])
    with pytest.raises(lib.DeployFailed, match="zoid6.wheelhouse"):
        lib.run_fill_wheelhouse("zoid6", _args())
