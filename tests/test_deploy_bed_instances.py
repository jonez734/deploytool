"""bed_instances.json: deploy stages and installs any registered bed instance, not only zoid6.

Each test writes its own registry under tmp_path and makes the loader read that file in place of the
packaged bed_instances.json. The JSON parsing and key filtering are the real code. No real account,
venv, or helper runs.
"""

import json
import pathlib

import pytest

from deploytool import lib


def _echoes(monkeypatch):
    out = []
    monkeypatch.setattr(lib.io, "echo", lambda msg, *a, **k: out.append(str(msg)))
    return out


def _instance(tmp_path, name):
    """A complete instance definition under tmp_path, registered in BED_INSTANCES by the caller."""
    root = tmp_path / name
    dist = root / "dist"
    dist.mkdir(parents=True)
    stage = root / "stage"
    stage.mkdir()
    (stage / f"{name}-1.0-py3-none-any.whl").write_bytes(b"wheel")
    manifest = stage / f"{name}-wheels.txt"
    manifest.write_text(f"{name}-1.0-py3-none-any.whl\n")
    helper = root / "build.sh"
    helper.write_text("#!/bin/sh\n")
    installer_src = root / "INSTALL.sh"
    installer_src.write_text("#!/bin/sh\n")
    venv = root / "venv"
    venv.mkdir()
    settings = {
        "account": name,
        "group": name,
        "account_dist": str(dist),
        "venv": str(venv),
        "installer": str(dist / "INSTALL.sh"),
        "installer_src": str(installer_src),
        "build_helper": str(helper),
        "stage": str(stage),
        "manifest": str(manifest),
    }
    return settings


def _use_registry(monkeypatch, path):
    """Make the loader read ``path`` (a temp registry) instead of the packaged file."""
    real = lib._load_bed_instances

    def from_file(source=None):
        with open(path, encoding="utf-8") as fh:
            return real(source=fh)

    monkeypatch.setattr(lib, "_load_bed_instances", from_file)


@pytest.fixture
def second_instance(tmp_path, monkeypatch):
    settings = _instance(tmp_path, "othered")
    entry = {k: v for k, v in settings.items()}
    registry = tmp_path / "bed_instances.json"
    registry.write_text(json.dumps({"othered": entry}))
    _use_registry(monkeypatch, registry)
    # The build helper is run for real by run_bed_instance_wheels; fake it so no build happens.
    monkeypatch.setattr(lib, "_run_subprocess", lambda cmd, **k: type("R", (), {"stdout": ""})())
    return settings


def test_second_instance_is_staged_from_its_own_settings(second_instance, monkeypatch):
    _echoes(monkeypatch)
    lib.run_bed_instance_wheels("othered", type("A", (), {"timeout": 5})())
    dist = pathlib.Path(second_instance["account_dist"])
    assert (dist / "othered-1.0-py3-none-any.whl").read_bytes() == b"wheel"
    assert (dist / "INSTALL.sh").exists()


def test_second_instance_venv_runs_its_installer_with_its_paths(second_instance, monkeypatch):
    pathlib.Path(second_instance["installer"]).write_text("#!/bin/sh\n")
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw["env"]
        return type("R", (), {"stdout": ""})()

    monkeypatch.setattr(lib, "_run_subprocess", fake)
    monkeypatch.setattr(lib, "_writable_by_me", lambda path: True)
    _echoes(monkeypatch)
    lib.run_bed_instance_venv("othered", type("A", (), {"timeout": 5})())
    assert seen["cmd"] == ["sh", second_instance["installer"]]
    assert seen["env"]["DIST"] == second_instance["account_dist"]
    assert seen["env"]["VENV"] == second_instance["venv"]


def test_dispatch_routes_a_registered_instance(second_instance, monkeypatch):
    _echoes(monkeypatch)
    called = []
    monkeypatch.setattr(lib, "run_bed_instance_wheels", lambda name, args: called.append(("wheels", name)))
    monkeypatch.setattr(lib, "run_bed_instance_venv", lambda name, args: called.append(("venv", name)))
    args = type("A", (), {"timeout": 5})()
    assert lib.run_make_deploy(args, "othered", "wheels") == 0
    assert lib.run_make_deploy(args, "othered", "venv") == 0
    assert called == [("wheels", "othered"), ("venv", "othered")]


def test_dispatch_dry_run_names_the_instance_paths(second_instance, monkeypatch):
    out = _echoes(monkeypatch)
    args = type("A", (), {"dry_run": True})()
    assert lib.run_make_deploy(args, "othered", "wheels") == 0
    assert second_instance["account_dist"] in "\n".join(out)


def test_unknown_instance_is_refused():
    with pytest.raises(KeyError, match="unknown bed instance"):
        lib.run_bed_instance_wheels("no-such-bed", type("A", (), {"timeout": 5})())


def test_settings_are_read_at_call_time(tmp_path, monkeypatch):
    """The file is read on each call, so an edit to it takes effect without reloading the module."""
    registry = tmp_path / "bed_instances.json"
    registry.write_text(json.dumps({"x": {f: "/a" for f in lib._INSTANCE_FIELDS}}))
    _use_registry(monkeypatch, registry)
    assert lib._instance_settings("x")["venv"] == "/a"
    registry.write_text(json.dumps({"x": {f: "/b" for f in lib._INSTANCE_FIELDS}}))
    assert lib._instance_settings("x")["venv"] == "/b"


def test_registry_file_drives_the_instance_list(second_instance):
    assert lib._bed_instance_names() == ["othered"]


def test_shipped_registry_names_zoid6():
    """The bed_instances.json that ships with deploytool still defines zoid6."""
    assert "zoid6" in lib._bed_instance_names()


def test_missing_field_is_reported_by_name(tmp_path, monkeypatch):
    registry = tmp_path / "bed_instances.json"
    registry.write_text(json.dumps({"partial": {"account": "partial"}}))
    _use_registry(monkeypatch, registry)
    with pytest.raises(ValueError, match="missing"):
        lib._instance_settings("partial")


def test_zoid6_wrappers_delegate_to_the_generic_functions(monkeypatch):
    calls = []
    monkeypatch.setattr(lib, "run_bed_instance_wheels", lambda name, args: calls.append(("wheels", name)))
    monkeypatch.setattr(lib, "run_bed_instance_venv", lambda name, args: calls.append(("venv", name)))
    args = type("A", (), {"timeout": 5})()
    lib.run_zoid6_wheels(args)
    lib.run_zoid6_venv(args)
    assert calls == [("wheels", "zoid6"), ("venv", "zoid6")]
