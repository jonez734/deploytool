"""The shared installer command: one pip call per bed instance, in either supply mode."""

import pytest

from deploytool import installer


pytestmark = pytest.mark.unit

VENV = "/home/zoid6/venv"
DIST = "/home/zoid6/dist-wheels"
WH = "/home/zoid6/wheelhouse"
WHEELS = ["bbsengine6-0.5.0.dev1-py3-none-any.whl", "bed-0.5.0.dev1-py3-none-any.whl"]


def test_index_mode_installs_from_the_index_with_internal_find_links():
    cmd = installer.build_pip_command(VENV, WHEELS, dist=DIST, mode="index")
    assert cmd[:4] == [f"{VENV}/bin/python", "-m", "pip", "install"]
    assert "--no-index" not in cmd
    assert cmd[cmd.index("--find-links") + 1] == DIST


def test_wheelhouse_mode_adds_no_index_and_the_wheelhouse():
    cmd = installer.build_pip_command(VENV, WHEELS, dist=DIST, mode="wheelhouse", wheelhouse=WH)
    assert "--no-index" in cmd
    links = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--find-links"]
    assert links == [DIST, WH]


def test_no_deps_is_never_used():
    for mode, wh in (("index", None), ("wheelhouse", WH)):
        cmd = installer.build_pip_command(VENV, WHEELS, dist=DIST, mode=mode, wheelhouse=wh)
        assert "--no-deps" not in cmd


def test_upgrade_strategy_is_only_if_needed():
    cmd = installer.build_pip_command(VENV, WHEELS, dist=DIST)
    i = cmd.index("--upgrade-strategy")
    assert cmd[i + 1] == "only-if-needed"


def test_wheels_keep_manifest_order_as_full_paths():
    cmd = installer.build_pip_command(VENV, WHEELS, dist=DIST)
    assert cmd[-2:] == [f"{DIST}/{WHEELS[0]}", f"{DIST}/{WHEELS[1]}"]


def test_setuptools_is_not_installed_into_the_venv():
    cmd = installer.build_pip_command(VENV, WHEELS, dist=DIST)
    assert "setuptools" not in cmd


def test_index_mode_refuses_a_wheelhouse():
    with pytest.raises(installer.InstallerConfigError, match="takes no wheelhouse"):
        installer.check_mode("index", WH)


def test_wheelhouse_mode_needs_a_wheelhouse():
    with pytest.raises(installer.InstallerConfigError, match="needs a wheelhouse"):
        installer.check_mode("wheelhouse", None)


def test_unknown_mode_is_refused():
    with pytest.raises(installer.InstallerConfigError, match="must be one of"):
        installer.check_mode("offline", None)


def test_empty_wheel_list_is_refused():
    with pytest.raises(installer.InstallerConfigError, match="no wheels"):
        installer.build_pip_command(VENV, [], dist=DIST)


def test_describe_mode_names_the_wheelhouse_when_offline():
    assert WH in installer.describe_mode("wheelhouse", WH)
    assert "package index" in installer.describe_mode("index", None)
