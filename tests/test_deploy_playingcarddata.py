"""playingcarddata deploys its venv sub into the zoid6 venv, as the card art package."""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")


@pytest.mark.unit
def test_playingcarddata_is_a_known_project():
    assert "playingcarddata" in lib.DEPENDENCIES
    assert "playingcarddata" in lib.TARGETS


@pytest.mark.unit
def test_playingcarddata_declares_only_the_venv_sub():
    assert lib.TARGETS["playingcarddata"] == ["venv"]


@pytest.mark.unit
def test_playingcarddata_installs_into_the_zoid6_venv():
    assert lib.VENV_LAYOUT["playingcarddata"] == "/home/zoid6/venv"


@pytest.mark.unit
def test_playingcarddata_venv_make_target_is_venv():
    assert lib.MAKE_TARGET_ALIASES[("playingcarddata", "venv")] == "venv"


@pytest.mark.unit
def test_playingcarddata_has_no_dependencies():
    assert lib.DEPENDENCIES["playingcarddata"] == []
