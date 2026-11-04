"""Per-instance install mode in bed_instances.json: index by default, wheelhouse with a directory.

A registry entry is validated when its settings are read, so a bad mode or a wheelhouse mismatch
stops the deploy before any install runs.
"""

import io
import json

import pytest

from deploytool import installer, lib


pytestmark = pytest.mark.unit

BASE = {
    "account": "zoid6", "group": "zoid6", "account_dist": "/d", "venv": "/v",
    "installer": "/i", "installer_src": "/s", "build_helper": "/b", "stage": "/st",
    "manifest": "/m",
}


def _settings(monkeypatch, **extra):
    entry = {**BASE, **extra}
    data = {"zoid6": entry}
    monkeypatch.setattr(lib, "_load_bed_instances", lambda source=None: data)
    return lib._instance_settings("zoid6")


def test_mode_defaults_to_index(monkeypatch):
    s = _settings(monkeypatch)
    assert s["mode"] == "index"
    assert s["wheelhouse"] is None


def test_wheelhouse_mode_takes_a_wheelhouse_directory(monkeypatch):
    s = _settings(monkeypatch, mode="wheelhouse", wheelhouse="/wh")
    assert s["mode"] == "wheelhouse"
    assert s["wheelhouse"] == "/wh"


def test_wheelhouse_path_expands_placeholders(monkeypatch):
    s = _settings(monkeypatch, mode="wheelhouse", wheelhouse="{stage}/wheelhouse")
    assert s["wheelhouse"] == "/st/wheelhouse"


def test_wheelhouse_mode_without_a_directory_is_refused(monkeypatch):
    with pytest.raises(installer.InstallerConfigError, match="needs a wheelhouse"):
        _settings(monkeypatch, mode="wheelhouse")


def test_index_mode_with_a_wheelhouse_is_refused(monkeypatch):
    with pytest.raises(installer.InstallerConfigError, match="takes no wheelhouse"):
        _settings(monkeypatch, mode="index", wheelhouse="/wh")


def test_unknown_mode_is_refused(monkeypatch):
    with pytest.raises(installer.InstallerConfigError, match="must be one of"):
        _settings(monkeypatch, mode="offline")


def test_the_packaged_registry_still_loads():
    """The shipped bed_instances.json (zoid6) reads in wheelhouse mode, with its wheelhouse directory."""
    settings = lib._instance_settings("zoid6")
    assert settings["mode"] == "wheelhouse"
    assert settings["wheelhouse"].endswith("/wheelhouse")
