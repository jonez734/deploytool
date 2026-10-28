"""Tests for the `pgsql` deploy sub-target, for `zoid6` and `bed`.

`pgsql` appends the identd mapping for the daemon login to the PostgreSQL server's
pg_hba.conf and pg_ident.conf, then reloads postgresql-18. It is an explicit step:
it is NOT part of `zoid6.prod` or `bed.prod`, so a normal prod deploy never reloads
the database.

These tests pin:

1. `TARGETS` advertises `pgsql` for both projects.
2. `MAKE_TARGET_ALIASES` maps each `pgsql` sub to `install-pgsql`.
3. `run_make_deploy` would run `make -C <project> install-pgsql`.
4. Neither `prod` chain includes `pgsql`.
5. Both Makefiles define an `install-pgsql` rule.
"""

from pathlib import Path

import pytest

import deploytool.lib


@pytest.mark.parametrize("project", ["zoid6", "bed"])
def test_targets_advertise_pgsql(project):
    """`deploy <project>.identd` must be a known sub-target."""
    assert "identd" in deploytool.lib.get_targets(project), (
        f"{project} TARGETS must contain 'pgsql'; "
        f"got {deploytool.lib.get_targets(project)!r}"
    )


@pytest.mark.parametrize("project", ["zoid6", "bed"])
def test_pgsql_alias_maps_to_install_pgsql(project):
    """The user-facing `pgsql` sub reaches the `install-pgsql` make rule."""
    key = (project, "identd")
    assert key in deploytool.lib.MAKE_TARGET_ALIASES, (
        f"MAKE_TARGET_ALIASES must contain {key!r}"
    )
    assert deploytool.lib.MAKE_TARGET_ALIASES[key] == "install-pgsql"


@pytest.mark.parametrize("project", ["zoid6", "bed"])
def test_run_make_deploy_builds_install_pgsql(project):
    """The make target `deploy <project>.identd` invokes is `install-pgsql`."""
    key = (project, "identd")
    target = deploytool.lib.MAKE_TARGET_ALIASES[key]
    assert target == "install-pgsql", (
        f"`deploy {project}.identd` must run `make -C {project} install-pgsql`; "
        f"the alias gives {target!r}"
    )


@pytest.mark.parametrize("project", ["zoid6", "bed"])
def test_pgsql_is_not_part_of_prod(project):
    """`pgsql` is explicit, never a dependency of `prod`."""
    deps = deploytool.lib.DEPENDENCIES.get(project, [])
    assert all(
        (d == "identd") is False for d in (x if isinstance(x, str) else x[1] for x in deps)
    ), f"{project} DEPENDENCIES must not name pgsql: {deps!r}"

    cond = deploytool.lib.CONDITIONAL_DEPENDENCIES.get(project, {})
    prod_deps = cond.get("prod", [])
    assert not any(
        (x == "identd" or (isinstance(x, tuple) and x[1] == "identd")) for x in prod_deps
    ), f"{project}.prod must not depend on pgsql: {prod_deps!r}"


@pytest.mark.parametrize("project", ["zoid6", "bed"])
def test_makefile_defines_install_pgsql(project):
    """Each project's Makefile must define an `install-pgsql` rule."""
    makefile = Path(deploytool.lib.SOURCE_BASE) / project / "Makefile"
    if project == "zoid6":
        makefile = Path(deploytool.lib.SOURCE_BASE) / "zoid6" / "src" / "Makefile"
    if project == "bed":
        makefile = Path(deploytool.lib.SOURCE_BASE) / "bed" / "src" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text(encoding="utf-8")
    assert "\ninstall-pgsql:" in text, f"{makefile} has no install-pgsql rule"
