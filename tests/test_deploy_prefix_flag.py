"""`--prefix PATH` on deploy: the venv install prefix. Unset means "use the project's default".

`--prefix` only sets DEPLOY_PREFIX for make; it does not change VENV_LAYOUT. Default behaviour is
unchanged when the flag is absent.
"""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")


@pytest.mark.unit
def test_prefix_defaults_to_none():
    args = lib.buildargs().parse_args(["letteredolive.venv"])
    assert args.prefix is None


@pytest.mark.unit
def test_prefix_is_carried_through():
    args = lib.buildargs().parse_args(["letteredolive.venv", "--prefix", "/var/lib/someother/venv"])
    assert args.prefix == "/var/lib/someother/venv"


@pytest.mark.unit
def test_prefix_applies_to_the_prod_sub_too():
    args = lib.buildargs().parse_args(["letteredolive.prod", "--prefix", "/x/venv"])
    assert args.prefix == "/x/venv"


import types  # noqa: E402

import deploytool.lib  # noqa: E402


def _completed(returncode=0):
    return types.SimpleNamespace(returncode=returncode, stdout="", stderr="")


def _run_with(monkeypatch, argv, project, sub, env_prefix=None):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(0)

    if env_prefix is not None:
        monkeypatch.setenv("DEPLOY_PREFIX", env_prefix)
    else:
        monkeypatch.delenv("DEPLOY_PREFIX", raising=False)
    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = lib.buildargs().parse_args(argv)
    assert deploytool.lib.run_make_deploy(args, project, sub) == 0
    return captured


@pytest.mark.unit
def test_prefix_flag_sets_deploy_prefix_for_make(monkeypatch):
    got = _run_with(monkeypatch, ["letteredolive.venv", "--prefix", "/var/lib/other/venv"],
                    "letteredolive", "venv")
    assert got["env"].get("DEPLOY_PREFIX") == "/var/lib/other/venv"


@pytest.mark.unit
def test_no_prefix_flag_strips_a_stale_shell_value(monkeypatch):
    got = _run_with(monkeypatch, ["letteredolive.venv"], "letteredolive", "venv",
                    env_prefix="/stale/from/shell")
    assert "DEPLOY_PREFIX" not in got["env"]


@pytest.mark.unit
def test_prod_gets_the_prefix_too(monkeypatch):
    got = _run_with(monkeypatch, ["letteredolive.prod", "--prefix", "/x/venv"],
                    "letteredolive", "prod")
    assert got["env"].get("DEPLOY_PREFIX") == "/x/venv"
