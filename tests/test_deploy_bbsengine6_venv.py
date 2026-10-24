"""`deploy bbsengine6.venv` builds and installs locally; bed.venv depends on it, not on prod.

bbsengine6.prod rsyncs to merlin over ssh, which fails under sudo (root has no key) and
must not run for a local venv install. bbsengine6.venv has no remote step.
"""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")


@pytest.mark.unit
def test_bbsengine6_declares_a_venv_sub():
    assert "venv" in lib.TARGETS["bbsengine6"]


@pytest.mark.unit
def test_bbsengine6_venv_maps_to_its_make_target():
    assert lib.MAKE_TARGET_ALIASES.get(("bbsengine6", "venv")) == "venv"


@pytest.mark.unit
def test_bed_venv_depends_on_bbsengine6_venv_not_prod():
    edges = lib.CONDITIONAL_DEPENDENCIES.get("bed", {}).get("venv", [])
    assert ("bbsengine6", "venv") in edges, edges
    assert ("bbsengine6", "prod") not in edges, edges


@pytest.mark.unit
def test_bbsengine6_venv_is_not_opt_in():
    # Installs the engine into the bed venv in a normal deploy, so it runs by default.
    assert "venv" not in lib.OPT_IN_SUBS


@pytest.mark.unit
def test_bed_venv_resolves_to_bbsengine6_venv_only():
    """`deploy --with-deps bed.venv` installs bbsengine6 locally and never runs its prod/bare deploy."""
    order = lib.resolve(["bed.venv"], with_deps=True)
    assert ("bbsengine6", "venv") in order, order
    assert ("bbsengine6", "prod") not in order, order
    assert ("bbsengine6", None) not in order, order
    assert order[-1] == ("bed", "venv"), order
