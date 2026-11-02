"""The zoid6 `root` sub: root-only host setup (sysusers, tmpfiles, identd), run explicitly.

Pins three things:

1. `zoid6` TARGETS advertise `root`.
2. `root` maps to the `install-root` make target, which zoid6's Makefile defines.
3. `root` is never a dependency of `zoid6.prod`, so a normal prod deploy never runs root steps.

The Makefile check is source-level: it reads zoid6's Makefile and does not run it.
"""

from pathlib import Path

import pytest

import deploytool.lib as lib


def test_zoid6_targets_advertise_root():
    assert "root" in lib.get_targets("zoid6")


def test_root_maps_to_install_root():
    assert lib.MAKE_TARGET_ALIASES[("zoid6", "root")] == "install-root"


def test_root_is_not_a_prod_dependency():
    deps = lib.DEPENDENCIES.get("zoid6", [])
    names = [d if isinstance(d, str) else d[1] for d in deps]
    assert "root" not in names
    cond = lib.CONDITIONAL_DEPENDENCIES.get("zoid6", {}).get("prod", [])
    assert not any(x == "root" or (isinstance(x, tuple) and x[1] == "root") for x in cond)


def test_root_is_not_an_opt_in_upload_sub():
    assert "root" not in lib.OPT_IN_SUBS


@pytest.mark.parametrize("makefile", [
    "zoid6/src/Makefile",
])
def test_zoid6_makefile_defines_install_root_with_a_root_check_first(makefile):
    text = (Path(lib.SOURCE_BASE) / makefile).read_text(encoding="utf-8")
    assert "\ninstall-root:" in text
    body = text.split("\ninstall-root:", 1)[1].split("\n\n", 1)[0]
    first_recipe = next(line for line in body.splitlines() if line.startswith("\t"))
    assert "id -u" in first_recipe and "-eq 0" in first_recipe, (
        "install-root must check for root before any other recipe line"
    )


def test_install_root_excludes_venv_and_systemd_steps():
    text = (Path(lib.SOURCE_BASE) / "zoid6/src/Makefile").read_text(encoding="utf-8")
    body = text.split("\ninstall-root:", 1)[1].split("\n\n", 1)[0]
    assert "install-venv" not in body
    assert "install-fhs" not in body
    assert "install-systemd" not in body
