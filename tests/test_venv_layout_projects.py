"""VENV_LAYOUT lists exactly the projects that install into a managed venv.

A project is listed only when it installs files into a venv. Projects with no install step yet are left out
until they gain one. mistermcfeely stays listed because it will need a .venv sub to deploy.
aolbonics is listed because its venv sub installs into whichever venv deploy targets (VENV_USER, or --prefix).
empyre and murdermotel are listed because they are bed-loaded programs whose venv sub installs into the zoid6 bed venv.
"""

import importlib

import pytest

lib = importlib.import_module("deploytool.lib")

EXPECTED = {
    "bed",
    "zoid6",
    "letteredolive",
    "backuptools",
    "casino",
    "deploytool",
    "bbsengine6",
    "mistermcfeely",
    "murdermotel",
    "aolbonics",
    "empyre",
    "moneyday",
}


@pytest.mark.unit
def test_venv_layout_lists_exactly_the_managed_venv_projects():
    assert set(lib.VENV_LAYOUT) == EXPECTED


@pytest.mark.unit
@pytest.mark.parametrize("project", ["atlas", "achilles", "asimov", "teos", "zoidoffice"])
def test_projects_without_a_venv_install_are_not_listed(project):
    assert project not in lib.VENV_LAYOUT
