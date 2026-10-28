"""zoid6.venv: the staged-wheel venv route.

zoid6.wheels syncs the wheels into the account home (root). zoid6.venv installs them as the account.
The engine is installed by bbsengine6's venv sub, not prod. Guards the venv path, the sub names,
the dependency order, and that the zoid6 conditional table keeps its www edge.
"""

import deploytool.lib as lib


def test_zoid6_venv_dir_is_the_account_home():
    assert lib.VENV_LAYOUT["zoid6"] == "/home/zoid6/venv"


def test_zoid6_declares_wheels_and_venv_subs():
    subs = lib.get_targets("zoid6")
    assert "wheels" in subs and "venv" in subs


def test_zoid6_venv_runs_after_wheels_and_engine_venv_not_prod():
    order = lib.resolve(["zoid6.venv"], with_deps=True)
    assert ("zoid6", "wheels") in order and ("zoid6", "venv") in order
    assert order.index(("zoid6", "wheels")) < order.index(("zoid6", "venv"))
    assert ("bbsengine6", "prod") not in order
    assert ("bbsengine6", "venv") in order


def test_wheels_and_venv_map_to_their_make_targets():
    assert lib.MAKE_TARGET_ALIASES[("zoid6", "wheels")] == "sync-wheels"
    assert lib.MAKE_TARGET_ALIASES[("zoid6", "venv")] == "install-wheels"


def test_zoid6_www_keeps_its_prod_edge():
    assert ("bbsengine6", "prod") in lib.resolve(["zoid6.www"], with_deps=True)


def test_shared_stays_unambiguous_with_the_new_subs():
    assert lib.resolve(["zoid6.shared"], with_deps=False) == [("zoid6", "shared")]


def test_zoid6_venv_runs_as_the_zoid6_account():
    """The account install runs as zoid6 (sudo -u zoid6), so install-wheels' own check passes."""
    assert lib.RUN_AS[("zoid6", "venv")] == "zoid6"
