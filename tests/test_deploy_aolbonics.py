"""aolbonics: a plain BBS install needs no zoid6; the zoid6 host sets --prefix explicitly.

jargon's client needs bed. Only the host that runs the zoid6 daemon needs zoid6, and it gets there by
passing --prefix (the zoid6 venv), not by a fixed registry path.
"""

import pytest

from deploytool import lib


def test_aolbonics_depends_on_bed_not_zoid6():
    assert lib.DEPENDENCIES["aolbonics"] == ["bed"]


def test_aolbonics_venv_resolution_pulls_no_zoid6():
    order = lib.resolve(["aolbonics.venv"], with_deps=True)
    assert not any(project == "zoid6" for project, _ in order)


def test_aolbonics_venv_depends_on_bbsengine6_venv_not_prod():
    """The engine is installed locally (bbsengine6.venv); the merlin prod umbrella never runs."""
    order = lib.resolve(["aolbonics.venv"], with_deps=True)
    assert order == [("bbsengine6", "venv"), ("aolbonics", "venv")]
    assert ("bbsengine6", "prod") not in order


def test_aolbonics_has_no_fixed_zoid6_venv_path():
    assert lib.VENV_LAYOUT["aolbonics"] is lib.VENV_USER


def test_aolbonics_venv_is_only_the_venv_sub():
    assert lib.get_targets("aolbonics") == ["venv"]
