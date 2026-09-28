"""Tests for the `teos.engine` sub-target.

teos gets a new sub under deploytool that wraps the bbsengine6 engine
stage+prod push into the teos.www chain:

  - `teos.engine` — `make deploy-engine` →
                     `make -C ../bbsengine6 engine-deploy-prod`
                     (the existing umbrella at
                     `bbsengine6/Makefile:233-234` which itself runs
                     `make -C engine deploy` = stage + merlin push).

The wrapper reuses the bbsengine6 engine-deploy-prod umbrella so the
rsync logic has one canonical home; the teos-side wrapper just adds
the deploytool-facing surface (`TARGETS["teos"]`) and the
`CONDITIONAL_DEPENDENCIES` wiring that pulls the engine install into
the teos.www chain.

The default zoidtechnologies.com /engine/ install is what
bbsengine6.engine-stage pushes, and it's also the vhost teos lives
under, so a teos deploy needs to (re)stage the engine entry-points
alongside its own vhost rsync. `ENGINE_DOCROOT` env var (set in
`deploytool/lib.py:run_make_deploy`) flows through to the underlying
bbsengine6 invocation; see `test_deploy_bbsengine6_engine.py` for the
env-var plumbing regression guards.

These tests are the deploy-side counterpart to the `deploy-engine`
wrapper in `teos/Makefile`. They guard against regressions where
someone removes the `engine` sub from `TARGETS["teos"]` (silently
reverting to a smaller TARGETS), breaks the make-rule wiring on the
teos side, removes the underlying `engine-deploy-prod` umbrella in
`bbsengine6/Makefile`, or breaks the `CONDITIONAL_DEPENDENCIES`
wiring that pulls teos.engine into the teos.www chain.
"""

import re
from pathlib import Path

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# TARGETS shape
# ---------------------------------------------------------------------------


def test_teos_targets_include_engine_sub():
    """`engine` must be in TARGETS['teos'].

    A single sub would force bare `deploy teos` to auto-pick,
    defeating the operator's intent to be forced to name a sub. A
    missing `engine` entry would silently drop the per-vhost /engine/
    install from the deploytool surface, leaving `deploy teos.engine`
    rejected as an unknown sub.
    """
    targets = deploytool.lib.get_targets("teos")
    assert "engine" in targets, (
        f"engine must be in teos TARGETS; got {targets!r}. "
        f"`deploy teos.engine` is the entry-point to the per-vhost /engine/ "
        f"install wired into CONDITIONAL_DEPENDENCIES['teos']['www']."
    )
    assert targets.count("engine") == 1


def test_teos_targets_tail_is_engine():
    """The new `engine` sub must be the trailing entry in TARGETS['teos'].

    The exact-list assertion for the historical pair (`www`, `tui`)
    is implicitly covered by `test_teoss_www_with_deps_walks_zoid6_shared_first`
    in `tests/test_deploy_with_deps.py` (which would break if `www` or
    `tui` were silently dropped). This test focuses on the new entry's
    position at the tail.
    """
    targets = deploytool.lib.get_targets("teos")
    assert targets[-1] == "engine", (
        f"engine must be the trailing sub in teos TARGETS; got tail {targets[-1]!r} "
        f"from {targets!r}."
    )


# ---------------------------------------------------------------------------
# Bare invocation: warn + exit (delegated to test_deploy_with_deps.py
# for the full chain assertions; here we just confirm the engine sub
# is reachable via the bare-base path).
# ---------------------------------------------------------------------------


def test_bare_teoss_lists_engine_sub_in_ambiguity_message(monkeypatch):
    """`deploy teos` (bare) lists `engine` in the ambiguity message
    so operators can discover it."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io,
        "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["teos"], with_deps=False)
    assert excinfo.value.code == 1

    out = "\n".join(msgs)
    assert "engine" in out, "resolver must list engine in the available subs"


# ---------------------------------------------------------------------------
# Explicit sub resolution
# ---------------------------------------------------------------------------


def test_teoss_engine_resolves_to_single_entry():
    """`deploy teos.engine` -> [('teos', 'engine')]."""
    order = deploytool.lib.resolve(["teos.engine"], with_deps=False)
    assert order == [("teos", "engine")]


# ---------------------------------------------------------------------------
# Shortest-unique-prefix resolution
# ---------------------------------------------------------------------------


def test_shortest_prefix_e_resolves_to_engine():
    """`deploy teos.e` -> engine (unique prefix within teos TARGETS).

    The historical pair `www` and `tui` don't start with `e`, so `e`
    is unambiguous and resolves to the new `engine` sub.
    """
    order = deploytool.lib.resolve(["teos.e"], with_deps=False)
    assert order == [("teos", "engine")]


# ---------------------------------------------------------------------------
# Makefile target wiring
# ---------------------------------------------------------------------------


def test_make_target_for_engine_sub_is_deploy_engine():
    """run_make_deploy must construct 'deploy-engine' for teos.engine."""
    project = "teos"
    sub = "engine"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-engine"


def test_teoss_makefile_defines_deploy_engine_target():
    """teos/Makefile must define a `deploy-engine:` target.

    Mirrors deploytool's "make target must exist" contract: if a
    TARGETS sub exists but no corresponding make rule, deploytool
    silently does the wrong thing (make fails with 'No rule to make
    target deploy-engine' but the deploy itself exits 0 because the
    subprocess was caught). Guarding here means a regression
    surfaces in CI, not in production.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "teos" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "deploy-engine:" in text, (
        "teos/Makefile must define a deploy-engine target. "
        f"Got:\n{text}"
    )


def test_teoss_makefile_lists_deploy_engine_as_phony():
    """deploy-engine must appear in the .PHONY list so `make` doesn't
    try to satisfy it with a same-named file in the working tree."""
    makefile = Path(deploytool.lib.SOURCE_BASE) / "teos" / "Makefile"
    text = makefile.read_text()
    phony_match = re.search(r"^\.PHONY:\s*(.+)$", text, re.MULTILINE)
    assert phony_match, "teos/Makefile must have a .PHONY: declaration"
    phony_line = phony_match.group(1)
    assert "deploy-engine" in phony_line, (
        f"deploy-engine must be in .PHONY; got: {phony_line!r}"
    )


def test_teoss_makefile_deploy_engine_delegates_to_bbsengine6_engine_deploy_prod():
    """The deploy-engine wrapper must delegate to bbsengine6's
    `engine-deploy-prod` umbrella (which itself runs `make -C engine
    deploy` = stage + merlin push). Without this delegation the
    wrapper is a no-op and `deploy teos.engine` silently does
    nothing.

    Convention is `deploy-engine: ; $(MAKE) -C ../bbsengine6
    engine-deploy-prod` — a single sub-make call so the rsync logic
    has one canonical home in bbsengine6/Makefile:233-234 (not
    duplicated here).
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "teos" / "Makefile"
    text = makefile.read_text()
    assert re.search(
        r"^deploy-engine:.*\n\s+\$\(MAKE\)\s+-C\s+\.\./bbsengine6\s+engine-deploy-prod",
        text,
        re.MULTILINE,
    ), (
        "teos/Makefile deploy-engine wrapper must delegate to "
        "`$(MAKE) -C ../bbsengine6 engine-deploy-prod`."
    )


# ---------------------------------------------------------------------------
# Underlying bbsengine6/Makefile shape (the wrapper points at this target)
# ---------------------------------------------------------------------------


def test_bbsengine6_makefile_defines_engine_deploy_prod_target():
    """bbsengine6/Makefile must define the `engine-deploy-prod` umbrella
    that teos/Makefile deploy-engine ultimately invokes. Without it,
    the wrapper fails with 'No rule to make target engine-deploy-prod'.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert re.search(r"^engine-deploy-prod:", text, re.MULTILINE), (
        "bbsengine6/Makefile must define an `engine-deploy-prod:` "
        f"target (the umbrella teos/Makefile deploy-engine delegates to). "
        f"Got:\n{text}"
    )


def test_bbsengine6_makefile_engine_deploy_prod_delegates_to_engine_submake():
    """`engine-deploy-prod` must delegate to `$(MAKE) -C engine deploy`
    (the stage + merlin-push umbrella at bbsengine6/engine/Makefile:19-20).

    Without the `$(MAKE) -C engine deploy` line the umbrella would
    be a no-op and `deploy teos.engine` would silently do nothing.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    m = re.search(
        r"^engine-deploy-prod:.*?(?=^\S|\Z)", text, re.MULTILINE | re.DOTALL
    )
    body = m.group(0) if m else ""
    assert "$(MAKE)" in body and "-C engine" in body and "deploy" in body, (
        "bbsengine6/Makefile engine-deploy-prod umbrella must delegate "
        "to `$(MAKE) -C engine deploy` so the rsync actually runs."
    )
