"""`deploy moneyday.venv` is a registered sub that installs into the zoid6 bed venv.

moneyday is a module the zoid6 bed loads through letteredolive, so it installs into /home/zoid6/venv
like murdermotel and empyre. Its venv sub depends on bbsengine6's venv sub, so the engine is in place
before the module's wheel installs.
"""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")


@pytest.mark.unit
def test_moneyday_is_a_known_project():
    assert "moneyday" in lib.DEPENDENCIES
    assert "moneyday" in lib.TARGETS


@pytest.mark.unit
def test_moneyday_declares_only_the_venv_sub():
    assert lib.TARGETS["moneyday"] == ["venv"]


@pytest.mark.unit
def test_moneyday_venv_installs_into_the_zoid6_venv():
    assert lib.VENV_LAYOUT["moneyday"] == "/home/zoid6/venv"


@pytest.mark.unit
def test_moneyday_depends_on_bbsengine6():
    assert "bbsengine6" in lib.DEPENDENCIES["moneyday"]


@pytest.mark.unit
def test_moneyday_venv_pulls_in_the_bbsengine6_venv_sub():
    assert lib.CONDITIONAL_DEPENDENCIES["moneyday"]["venv"] == [("bbsengine6", "venv")]


@pytest.mark.unit
def test_moneyday_venv_make_target_is_venv():
    assert lib.MAKE_TARGET_ALIASES[("moneyday", "venv")] == "venv"


@pytest.mark.unit
def test_moneyday_is_not_in_the_default_deploy_chain():
    # Only the explicitly named sub runs; moneyday is not pulled in by any other project.
    for project, deps in lib.DEPENDENCIES.items():
        if project != "moneyday":
            assert "moneyday" not in deps, project
