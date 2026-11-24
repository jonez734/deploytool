"""A venv deploy for a project with no fixed venv path requires --prefix.

bed, bbsengine6, casino, and the other projects whose VENV_LAYOUT entry is None have no venv of their own. Without
--prefix, deploy used to fall back to the calling account's active venv, and when there was none (for example zoid6
running the deploy) the failure appeared deep inside make as "command not found". The check now stops before make runs,
and names --prefix.
"""

import pytest

import deploytool.lib as lib

NO_FIXED_VENV = sorted(k for k, v in lib.VENV_LAYOUT.items() if v is None and k not in lib.USER_VENV_PROJECTS)


@pytest.mark.unit
@pytest.mark.parametrize("project", NO_FIXED_VENV)
def test_a_venv_deploy_without_a_prefix_is_refused_with_a_prefix_message(project, capsys):
    with pytest.raises(SystemExit) as ctx:
        lib.require_prefix_for_venv(project, prefix=None, sub="venv")
    assert ctx.value.code != 0
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "DEPLOY STOPPED" in out
    assert "--prefix is required" in out
    assert f"deploy --prefix /home/zoid6/venv {project}.venv" in out


@pytest.mark.unit
@pytest.mark.parametrize("project", NO_FIXED_VENV)
def test_a_venv_deploy_with_a_prefix_passes(project):
    assert lib.require_prefix_for_venv(project, prefix="/home/zoid6/venv", sub="venv") is None


@pytest.mark.unit
def test_a_project_with_a_fixed_venv_does_not_need_a_prefix():
    assert lib.require_prefix_for_venv("zoid6", prefix=None, sub="venv") is None


@pytest.mark.unit
@pytest.mark.parametrize("sub", ["tui", "www", "engine", "prod"])
def test_non_venv_targets_are_not_checked(sub):
    assert lib.require_prefix_for_venv("bed", prefix=None, sub=sub) is None
