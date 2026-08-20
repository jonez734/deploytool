"""Tests for `deploy getdate_next.tui` and the underlying make pipeline.

These tests are regression guards for two related `PREPARE_BUILD`
invariants on `getdate_next/Makefile`:

1. **Foreign-owned `build/` EPERMs the chmod.** When a prior build
   ran as a different uid, the leftover `build/` is owned by that
   uid and we cannot `chmod` it (only the owner can chmod). Without
   the rename, the chmod step in `PREPARE_BUILD` fails with EPERM
   and the build aborts. This is the failure mode `deploy
   getdate_next` hit on 2026-08-20.

2. **`chmod 1775`, not `chmod g-s`.** `chmod g-s` is umask-dependent
   and on a setgid parent we don't own it can itself EPERM. Mode
   1775 (sticky + rwxrwxr-x) is the desired resting state for
   shared build/ dirs and pins the mode idempotently. setgid is
   intentionally NOT set because setuptools' `shutil.copystat`
   mirrors build/'s mode onto dist-info, and a setgid'd dist-info
   EPERMs the `bdist_wheel` step in SELinux+NoNewPrivs containers.

The text-based assertions here mirror
`test_deploy_bed_tui.py::test_prepare_build_renames_foreign_owned_build_dir`
and
`test_deploy_bed_tui.py::test_prepare_build_pins_build_dir_to_mode_1775`,
applied to `getdate_next/Makefile` instead of `bed/Makefile`.
"""

import deploytool.lib
from pathlib import Path


SOURCE_BASE = Path(deploytool.lib.SOURCE_BASE)
GETDATE_DIR = SOURCE_BASE / deploytool.lib.PROJECT_DIRS.get(
    "getdate_next", "getdate_next"
)


def test_getdate_next_tui_resolves_to_getdate_next_with_tui_sub():
    """`deploy getdate_next.tui` resolves to `getdate_next` (tui).

    `getdate_next` has no transitive dependencies (`DEPENDENCIES`
    entry is `[]`); the `tui` sub-target is routed to the `venv`
    make target via `MAKE_TARGET_ALIASES`, same shape as `bed`'s
    `tui` -> `venv` mapping.
    """
    order = deploytool.lib.resolve(["getdate_next.tui"])
    assert order == [("getdate_next", "tui")]
    assert deploytool.lib.MAKE_TARGET_ALIASES[("getdate_next", "tui")] == "venv"


def test_prepare_build_renames_foreign_owned_build_dir():
    """`PREPARE_BUILD` must rename a not-owned-by-us `build/` out of the way.

    When a prior build run was performed by a different uid, the
    leftover `build/` directory is owned by that uid and we cannot
    `chmod` it (only the owner can chmod). Without the rename, the
    chmod step in `PREPARE_BUILD` fails with EPERM and the build
    aborts. Guards against accidental removal of the rename logic
    on `getdate_next/Makefile` specifically (bed has its own
    pinned tests).
    """
    makefile = GETDATE_DIR / "Makefile"
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
    """`PREPARE_BUILD` must set `build/` to mode 1775 (sticky + rwxrwxr-x).

    Mode 1775 is the desired resting state for shared build/ dirs:
    - sticky prevents cross-user file stomping inside the dir;
    - group write lets other users in the build group rebuild;
    - setgid is intentionally NOT set, because setuptools' copystat
      mirrors build/'s mode onto dist-info, and a setgid'd dist-info
      EPERMs the bdist_wheel step in SELinux+NoNewPrivs containers.
    """
    makefile = GETDATE_DIR / "Makefile"
    text = makefile.read_text()

    prepare_block = text.split("PREPARE_BUILD = ", 1)[1].split("\n\n", 1)[0]

    assert "chmod 1775" in prepare_block, (
        "PREPARE_BUILD must pin build/ to mode 1775 (sticky + rwxrwxr-x). "
        "Got:\n" + prepare_block
    )
    # Also confirm we did NOT regress to the old setgid-leaking mode:
    assert "chmod g-s" not in prepare_block, (
        "PREPARE_BUILD should not use `chmod g-s` (the old behaviour left "
        "build/ mode dependent on umask, which can drop the sticky bit). "
        "Use `chmod 1775` to pin the mode explicitly. Got:\n" + prepare_block
    )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
