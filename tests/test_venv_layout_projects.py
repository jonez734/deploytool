"""VENV_LAYOUT lists exactly the projects that install into a managed venv.

A project is listed only when it installs files into a venv. Projects with no install step yet are left out
until they gain one; mistermcfeely and murdermotel stay listed because they will need a .venv sub to deploy.
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
}


@pytest.mark.unit
def test_venv_layout_lists_exactly_the_managed_venv_projects():
    assert set(lib.VENV_LAYOUT) == EXPECTED


@pytest.mark.unit
@pytest.mark.parametrize("project", ["atlas", "empyre", "achilles", "asimov", "teos", "zoidoffice"])
def test_projects_without_a_venv_install_are_not_listed(project):
    assert project not in lib.VENV_LAYOUT
