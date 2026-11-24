"""setupimagebbs is a deploy project with a venv target that installs into the user's venv, with no --prefix.

Other VENV_USER projects (bed, bbsengine6, casino, deploytool, aolbonics) still require --prefix; setupimagebbs is the
one listed in USER_VENV_PROJECTS, which exempts it from that check.
"""

import pytest

import deploytool.lib as lib


@pytest.mark.unit
def test_setupimagebbs_has_a_venv_target():
    assert lib.TARGETS["setupimagebbs"] == ["venv"]


@pytest.mark.unit
def test_setupimagebbs_installs_into_the_user_venv():
    assert lib.VENV_LAYOUT["setupimagebbs"] is lib.VENV_USER


@pytest.mark.unit
def test_setupimagebbs_pulls_in_bbsengine6_venv_first():
    assert ("bbsengine6", "venv") in lib.CONDITIONAL_DEPENDENCIES["setupimagebbs"]["venv"]


@pytest.mark.unit
def test_setupimagebbs_venv_does_not_require_prefix():
    assert lib.require_prefix_for_venv("setupimagebbs", prefix=None, sub="venv") is None


@pytest.mark.unit
@pytest.mark.parametrize("project", ["bed", "casino", "bbsengine6", "deploytool", "aolbonics"])
def test_other_user_venv_projects_still_require_prefix(project):
    with pytest.raises(SystemExit):
        lib.require_prefix_for_venv(project, prefix=None, sub="venv")
