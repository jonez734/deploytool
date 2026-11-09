"""asimov deploys its venv sub into the zoid6 venv, as a program the zoid6 bed loads."""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")


@pytest.mark.unit
def test_asimov_declares_only_the_venv_sub():
    assert lib.TARGETS["asimov"] == ["venv"]


@pytest.mark.unit
def test_asimov_installs_into_the_zoid6_venv():
    assert lib.VENV_LAYOUT["asimov"] == "/home/zoid6/venv"


@pytest.mark.unit
def test_asimov_venv_make_target_is_venv():
    assert lib.MAKE_TARGET_ALIASES[("asimov", "venv")] == "venv"


@pytest.mark.unit
def test_asimov_keeps_its_dependencies():
    assert lib.DEPENDENCIES["asimov"] == ["bbsengine6", "zoid6"]
