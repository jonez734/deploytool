"""`deploy letteredolive.venv` and `deploy letteredolive.prod` are valid subs; a bare name is ambiguous.

prod is opt-in (never runs in a default deploy); both accept --prefix.
"""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")


@pytest.mark.unit
def test_letteredolive_declares_venv_and_prod_subs():
    assert set(lib.TARGETS["letteredolive"]) == {"venv", "prod"}


@pytest.mark.unit
def test_prod_is_opt_in():
    assert "prod" in lib.OPT_IN_SUBS


@pytest.mark.unit
def test_venv_and_prod_both_accept_prefix():
    for sub in ("venv", "prod"):
        args = lib.buildargs().parse_args([f"letteredolive.{sub}", "--prefix", "/x/venv"])
        assert args.prefix == "/x/venv"


@pytest.mark.unit
def test_letteredolive_venv_depends_on_bbsengine6_venv_only():
    """letteredolive.venv pulls bbsengine6.venv (local) and never bbsengine6 prod/umbrella (merlin rsync)."""
    order = lib.resolve(["letteredolive.venv"], with_deps=True)
    assert ("bbsengine6", "venv") in order
    assert ("letteredolive", "venv") in order
    assert order.index(("bbsengine6", "venv")) < order.index(("letteredolive", "venv"))
    assert not any(name == "bbsengine6" and sub in (None, "prod") for name, sub in order)


@pytest.mark.unit
@pytest.mark.parametrize("sub,target", [("venv", "venv"), ("prod", "prod")])
def test_letteredolive_subs_map_to_their_make_targets(sub, target):
    """letteredolive's Makefile names its targets `venv` and `prod`, not `deploy-venv` / `deploy-prod`."""
    assert lib.MAKE_TARGET_ALIASES.get(("letteredolive", sub)) == target
