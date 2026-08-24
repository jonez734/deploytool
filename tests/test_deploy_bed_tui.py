"""Tests for `deploy bed.tui` and the underlying make pipeline.

The test in this module exists primarily as a regression guard for the
egg-info absolute-path trap: when a stale `src/<pkg>.egg-info/SOURCES.txt`
contains absolute paths (e.g. from a prior `pip install -e .`), a later
`python -m build` invocation fails with:

    setup script specifies an absolute path:
        /home/opencode/data/work/bed/src/bed/__init__.py
    setup() arguments must *always* be /-separated paths relative to the
    setup.py directory, *never* absolute paths.

`deploy bed.tui` resolves through `deploytool.lib.run_make_deploy` to
`make -C /home/opencode/data/work/bed deploy-venv` (because
`MAKE_TARGET_ALIASES = {("bed", "tui"): "venv"}`). The regression test
exercises that exact make target so any recurrence of the egg-info trap
shows up here instead of breaking production deploys.
"""

import os
import subprocess
from pathlib import Path

import pytest

import deploytool.lib


SOURCE_BASE = Path(deploytool.lib.SOURCE_BASE)
BED_DIR = SOURCE_BASE / deploytool.lib.PROJECT_DIRS.get("bed", "bed")


def test_bed_tui_resolves_to_bed_with_tui_sub():
    """`deploy bed.tui` resolves to the `bed` project with `tui` sub-target.

    `bbsengine6` is pulled in with the matching `tui` sub-target so the
    bbsengine6 build matches what the user asked for (the conditional
    dependency was added to `CONDITIONAL_DEPENDENCIES["bed"]["tui"]`).
    The exact make-target (`deploy-venv` for bed, `deploy-tui` for
    bbsengine6) is applied at run time via `MAKE_TARGET_ALIASES`, not in
    the resolve output.
    """
    order = deploytool.lib.resolve(["bed.tui"], with_deps=True)
    assert order == [("bbsengine6", "tui"), ("bed", "tui")]
    assert deploytool.lib.MAKE_TARGET_ALIASES[("bed", "tui")] == "venv"


def test_bed_tui_pulls_bbsengine6_tui_not_bare_bbsengine6():
    """User-facing requirement: `deploy bed.tui` must deploy `bbsengine6.tui`.

    Regression guard: without the `CONDITIONAL_DEPENDENCIES["bed"]["tui"]`
    entry, `bed.tui` would pull bare `bbsengine6` (sub=None) and run
    `make deploy` instead of `make deploy-tui`. The bbsengine6 bare
    deploy does full web+php+skin rsync that a tui-only consumer does
    not need and that may fail or hang in restricted environments.
    """
    order = deploytool.lib.resolve(["bed.tui"], with_deps=True)

    bbsengine6_entries = [entry for entry in order if entry[0] == "bbsengine6"]
    assert bbsengine6_entries, "bed.tui must depend on bbsengine6"
    assert all(sub == "tui" for _, sub in bbsengine6_entries), (
        f"bed.tui must pull bbsengine6.tui (matching sub-target), "
        f"but resolve returned: {bbsengine6_entries}"
    )

    # And the conditional dependency itself is wired correctly:
    assert "tui" in deploytool.lib.CONDITIONAL_DEPENDENCIES["bed"]
    assert ("bbsengine6", "tui") in deploytool.lib.CONDITIONAL_DEPENDENCIES["bed"]["tui"]


def test_bed_venv_keeps_bare_bbsengine6_dep():
    """`deploy bed.venv` does NOT pull `bbsengine6.venv` because that
    sub-target does not exist in bbsengine6's TARGETS. It keeps the
    unconditional bare `bbsengine6` dep from DEPENDENCIES.
    """
    order = deploytool.lib.resolve(["bed.venv"], with_deps=True)
    bbsengine6_entries = [entry for entry in order if entry[0] == "bbsengine6"]
    assert bbsengine6_entries == [("bbsengine6", None)], (
        f"bed.venv should pull bare bbsengine6, got: {bbsengine6_entries}"
    )


def test_make_target_for_bed_tui_is_deploy_venv():
    """`run_make_deploy` must build the `deploy-venv` target for `bed.tui`.

    Reproduces the cmd-vector construction from `lib.run_make_deploy`
    without invoking subprocess, so the assertion catches regressions in
    the alias mapping itself.
    """
    project = "bed"
    sub = "tui"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    project_dir = f"{deploytool.lib.SOURCE_BASE}/{deploytool.lib.PROJECT_DIRS.get(project, project)}"
    assert target == "deploy-venv"
    assert project_dir == str(BED_DIR)


def test_deploy_bed_tui_make_target_succeeds():
    """End-to-end regression test: `make deploy-venv` must succeed.

    This is the actual make target `deploy bed.tui` invokes. The egg-info
    trap previously broke this command with:

        Error: setup script specifies an absolute path:
            /home/opencode/data/work/bed/src/bed/__init__.py
        ERROR Backend subprocess exited when trying to invoke build_wheel

    The Makefile now has `deploy-venv: clean-egg-info` which wipes any
    stale `*.egg-info/` directory (root or under `src/`) before invoking
    `python -m build`, so the trap cannot recur.

    We deliberately invoke `make deploy-venv` *without* `clean-egg-info`
    as an explicit prerequisite target — that mirrors what
    `deploytool.lib.run_make_deploy` does (`make -C <dir> deploy-venv`
    with no extra targets). The prereq inside the Makefile is the only
    thing standing between us and the trap, so it must do its job.
    """
    assert BED_DIR.is_dir(), f"bed source tree not found at {BED_DIR}"

    result = subprocess.run(
        ["make", "deploy-venv"],
        cwd=str(BED_DIR),
        capture_output=True,
        text=True,
        timeout=600,
    )

    combined = result.stdout + result.stderr

    assert result.returncode == 0, (
        f"make deploy-venv exited {result.returncode}.\n"
        f"--- stdout (tail) ---\n{result.stdout[-2000:]}\n"
        f"--- stderr (tail) ---\n{result.stderr[-2000:]}"
    )

    assert "absolute path" not in combined, (
        "egg-info absolute-path trap detected in deploy output. "
        "The bed Makefile's `clean-egg-info` prereq should prevent this; "
        "investigate whether `src/Makefile install` cleanup was removed.\n"
        f"--- stderr ---\n{result.stderr[-2000:]}"
    )

    assert (
        "Successfully installed bed" in combined
        or "bed is already installed" in combined
    ), (
        "make deploy-venv did not install (or detect existing) the bed wheel. "
        "Expected either 'Successfully installed bed' or "
        "'bed is already installed' in pip output.\n"
        f"--- stdout (tail) ---\n{result.stdout[-2000:]}\n"
        f"--- stderr (tail) ---\n{result.stderr[-2000:]}"
    )


def test_clean_egg_info_target_exists_and_wipes_in_tree_egg_info():
    """The `clean-egg-info` target is what prevents the trap from recurring.

    Seeds a fake egg-info under `src/bed.egg-info/` (with the absolute
    path layout the trap historically produced), runs `make clean-egg-info`,
    then asserts the dir is gone.
    """
    egg_info = BED_DIR / "src" / "bed.egg-info"
    sourses = egg_info / "SOURCES.txt"

    try:
        egg_info.mkdir(parents=True, exist_ok=True)
        sourses.write_text(
            "/home/opencode/data/work/bed/src/bed/__init__.py\n"
            "src/bed/__init__.py\n"
        )

        result = subprocess.run(
            ["make", "clean-egg-info"],
            cwd=str(BED_DIR),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"make clean-egg-info failed:\n{result.stderr}"
        )
        assert not egg_info.exists(), (
            f"clean-egg-info did not remove {egg_info}"
        )
    finally:
        subprocess.run(
            ["rm", "-rf", str(egg_info)],
            check=False,
        )


def test_src_makefile_install_cleans_up_egg_info():
    """`src/Makefile install` must not leave a poisoned egg-info behind.

    The editable install (`pip install -e .`) creates `src/bed.egg-info/`
    with absolute paths in SOURCES.txt. The src Makefile's `install`
    recipe must remove that dir at the end so the next non-editable build
    is not poisoned.
    """
    src_makefile = BED_DIR / "src" / "Makefile"
    assert src_makefile.is_file(), f"{src_makefile} not found"

    text = src_makefile.read_text()
    install_block = text.split("install: version", 1)[1].split("\n\n", 1)[0]

    assert "egg-info" in install_block, (
        "src/Makefile install recipe must clean up its own egg-info. "
        f"Got:\n{install_block}"
    )


def test_prepare_build_renames_foreign_owned_build_dir():
    """PREPARE_BUILD must rename a foreign-owned $(1)/build/ out of the way.

    When a prior build run was performed by a different uid, the
    leftover `build/` directory is owned by that uid and we cannot
    `chmod` it (only the owner can chmod). Without the rename, the
    chmod step in PREPARE_BUILD fails with EPERM and the build aborts.

    Guards against accidental removal of the rename logic.
    """
    makefile = BED_DIR / "Makefile"
    text = makefile.read_text()

    prepare_block = text.split("PREPARE_BUILD = ", 1)[1].split("\n\n", 1)[0]

    assert "mv" in prepare_block, (
        "PREPARE_BUILD must rename foreign-owned build/ dirs out of the "
        "way before mkdir -p. Got:\n" + prepare_block
    )
    assert "build.stale" in prepare_block, (
        "PREPARE_BUILD must rename to build.stale.* (not just rm). Got:\n"
        + prepare_block
    )
    assert "[ ! -O" in prepare_block or "! -O" in prepare_block, (
        "PREPARE_BUILD must gate the rename on a not-owned-by-us check "
        "so it doesn't move our own build/ when we own it. Got:\n"
        + prepare_block
    )


def test_prepare_build_pins_build_dir_to_mode_1775():
    """PREPARE_BUILD must set build/ to mode 1775 (sticky + rwxrwxr-x).

    Mode 1775 is the desired resting state for shared build/ dirs:
    - sticky prevents cross-user file stomping inside the dir;
    - group write lets other users in the build group rebuild;
    - setgid is intentionally NOT set, because setuptools' copystat
      mirrors build/'s mode onto dist-info, and a setgid'd dist-info
      EPERMs the bdist_wheel step in SELinux+NoNewPrivs containers.

    The chmod is expressed as `chmod g-s,+t` (drop the setgid bit the
    parent dir inherited onto the freshly-mkdir'd build/, then add the
    sticky bit). The numeric form `chmod 1775` is functionally
    equivalent but trips a kernel restriction on BTRFS/SELinux setups
    where the parent directory's setgid bit blocks the owner from
    clearing it via the numeric mode. The symbolic form works because
    the kernel only restricts numeric mode changes that would remove
    the inherited setgid bit; symbol-mode `g-s` is allowed.
    """
    makefile = BED_DIR / "Makefile"
    text = makefile.read_text()

    prepare_block = text.split("PREPARE_BUILD = ", 1)[1].split("\n\n", 1)[0]

    # Drop the inherited setgid AND add the sticky bit (resting mode 1775):
    assert "g-s" in prepare_block and "+t" in prepare_block, (
        "PREPARE_BUILD must drop the inherited setgid and add the "
        "sticky bit so build/ rests at mode 1775 (sticky + rwxrwxr-x). "
        "Got:\n" + prepare_block
    )
    # Numeric form `chmod 1775` is forbidden because it fails on BTRFS+
    # SELinux setups where the parent dir's setgid bit prevents the
    # owner from clearing it via the numeric mode:
    assert "chmod 1775" not in prepare_block, (
        "PREPARE_BUILD must not use numeric `chmod 1775`: it fails "
        "on BTRFS+SELinux setups where the parent dir's setgid bit "
        "blocks the owner from clearing it. Use `chmod g-s,+t` instead. "
        "Got:\n" + prepare_block
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
