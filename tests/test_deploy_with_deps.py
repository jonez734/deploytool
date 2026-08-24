"""Tests for the `--with-deps` flag and bare-base ambiguity behavior.

Bare-base rules (see `lib.resolve` docstring and SPECS.md §4):

- A bare base with `TARGETS` containing multiple subs is ambiguous.
  `lib.resolve()` calls `sys.exit(1)` with the available subs listed.
  Caller must name at least one sub.
- A bare base with `TARGETS` containing exactly one sub auto-picks that
  sub (no choice to make).
- A bare base with no `TARGETS` (e.g. `getdate_next`'s alias
  `mistermcfeely`) has nothing to choose from; the bare `make deploy`
  target runs.
- Under `--with-deps` (`with_deps=True`), bare-base with `TARGETS`
  auto-expands to all subs AND walks the full transitive dep chain.
  This is the "build the whole thing" intent shortcut.

The `--with-deps` flag controls dep walking independently:

- `with_deps=False` (default): no transitive deps are pulled in.
  Only the projects the caller named run.
- `with_deps=True`: the topo-sorted dep chain runs for each requested
  project. `--with-deps` is orthogonal to `--editable`.
"""

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# Bare-base ambiguity (list subs, exit 1)
# ---------------------------------------------------------------------------


def test_bare_casino_with_multiple_subs_is_ambiguous(monkeypatch):
    """`deploy casino` with 2+ subs in TARGETS lists them and exits 1."""
    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["casino"], with_deps=False)
    assert excinfo.value.code == 1


def test_bare_bed_with_three_subs_lists_all_three(monkeypatch):
    """`deploy bed` (with `["tui", "venv", "prod"]`) lists all three including prod."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit):
        deploytool.lib.resolve(["bed"], with_deps=False)
    out = "\n".join(msgs)
    assert "bed" in out
    assert "tui" in out
    assert "venv" in out
    assert "prod" in out


def test_bare_casino_with_deps_auto_expands_both_subs():
    """Per Q2-B: bare-base under --with-deps auto-expands to all subs.

    `deploy --with-deps casino` (bare) IS the "build the whole thing"
    shortcut. It runs both `casino.tui` and `casino.www` (and walks their
    full dep chains). Without --with-deps, the bare form is ambiguous.
    """
    order = deploytool.lib.resolve(["casino"], with_deps=True)
    casino_subs = [s for _, s in order if _ == "casino"]
    assert casino_subs == ["tui", "www"]


def test_multi_project_no_subs_lists_each(monkeypatch):
    """`deploy casino bed` (no subs) lists each project and exits 1."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit):
        deploytool.lib.resolve(["casino", "bed"], with_deps=False)
    out = "\n".join(msgs)
    assert "casino" in out
    assert "bed" in out


# ---------------------------------------------------------------------------
# Bare-base single-sub auto-pick
# ---------------------------------------------------------------------------


def test_bare_single_sub_target_auto_picks_that_sub():
    """`deploy getdate_next` (TARGETS has one sub) auto-picks `tui`."""
    order = deploytool.lib.resolve(["getdate_next"], with_deps=False)
    assert order == [("getdate_next", "tui")]


def test_bare_single_sub_target_auto_picks_even_without_with_deps():
    """Auto-pick of single sub is independent of --with-deps."""
    order = deploytool.lib.resolve(["getdate_next"])
    assert order == [("getdate_next", "tui")]


# ---------------------------------------------------------------------------
# Projects without TARGETS — bare deploy
# ---------------------------------------------------------------------------


def test_bare_project_without_targets_runs_bare():
    """Projects with no TARGETS run bare `make deploy` (no ambiguity possible)."""
    order = deploytool.lib.resolve(["mistermcfeely"], with_deps=False)
    assert order == [("mistermcfeely", None)]


# ---------------------------------------------------------------------------
# Explicit sub resolution: with_deps=False (no transitive deps)
# ---------------------------------------------------------------------------


def test_explicit_sub_no_deps_no_transitive_pull():
    """`deploy casino.tui` with `with_deps=False` runs only casino.tui."""
    order = deploytool.lib.resolve(["casino.tui"], with_deps=False)
    assert order == [("casino", "tui")]


def test_explicit_sub_no_deps_two_subs():
    """`deploy casino.tui casino.www` runs both, no shared deps."""
    order = deploytool.lib.resolve(
        ["casino.tui", "casino.www"], with_deps=False
    )
    assert order == [("casino", "tui"), ("casino", "www")]


def test_explicit_sub_for_no_deps_project():
    """`deploy bbsengine6.tui` runs only that sub (no deps exist anyway)."""
    order = deploytool.lib.resolve(["bbsengine6.tui"], with_deps=False)
    assert order == [("bbsengine6", "tui")]


# ---------------------------------------------------------------------------
# --with-deps: full chain (auto-expand subs)
# ---------------------------------------------------------------------------


def test_with_deps_bare_casino_auto_expands_both_subs_plus_deps():
    """`deploy --with-deps casino` runs casino.tui + casino.www + full chain."""
    order = deploytool.lib.resolve(["casino"], with_deps=True)
    assert order == [
        ("bbsengine6", "www"),
        ("bbsengine6", "tui"),
        ("bed", "tui"),
        ("casino", "tui"),
        ("casino", "www"),
    ]


def test_with_deps_bare_bed_auto_expands_all_three_subs():
    """`deploy --with-deps bed` auto-expands tui+venv+prod (prod is opt-in here).

    bed.tui and bed.venv both alias to the same make target (`deploy-venv`),
    so the dedup pass collapses them to one entry. The assertion only
    checks the surviving-aliased sub is present, plus prod (which
    survives because the prod opt-in drop is keyed on explicit_subs
    and --with-deps populates explicit_subs for every auto-expanded sub).
    """
    order = deploytool.lib.resolve(["bed"], with_deps=True)
    bed_entries = [s for _, s in order if _ == "bed"]
    assert "prod" in bed_entries, f"bed.prod missing from {bed_entries}"
    assert any(s in ("tui", "venv") for s in bed_entries), (
        f"bed.tui or bed.venv missing from {bed_entries}"
    )


def test_with_deps_explicit_sub_walks_chain():
    """`deploy --with-deps casino.tui` walks full chain for that sub."""
    order = deploytool.lib.resolve(["casino.tui"], with_deps=True)
    assert order == [
        ("bbsengine6", "tui"),
        ("bed", "tui"),
        ("casino", "tui"),
    ]


def test_with_deps_explicit_subs_combined():
    """`deploy --with-deps casino.tui casino.www` merges chains."""
    order = deploytool.lib.resolve(
        ["casino.tui", "casino.www"], with_deps=True
    )
    assert order == [
        ("bbsengine6", "www"),
        ("bbsengine6", "tui"),
        ("bed", "tui"),
        ("casino", "tui"),
        ("casino", "www"),
    ]


def test_with_deps_no_chain_when_none_exists():
    """bbsengine6 has no transitive deps; with/without --with-deps is identical."""
    without = deploytool.lib.resolve(["bbsengine6.tui"], with_deps=False)
    with_deps = deploytool.lib.resolve(["bbsengine6.tui"], with_deps=True)
    assert without == with_deps == [("bbsengine6", "tui")]


# ---------------------------------------------------------------------------
# Backwards-compat: default kwarg preserves old behavior for explicit subs
# ---------------------------------------------------------------------------


def test_resolve_default_kwarg_is_false():
    """`resolve([...])` (no kwarg) defaults to with_deps=False."""
    no_kwarg = deploytool.lib.resolve(["casino.tui"])
    explicit_false = deploytool.lib.resolve(["casino.tui"], with_deps=False)
    assert no_kwarg == explicit_false == [("casino", "tui")]


# ---------------------------------------------------------------------------
# Unknown sub-target still errors (unchanged behavior)
# ---------------------------------------------------------------------------


def test_unknown_sub_target_errors(monkeypatch):
    """Naming a sub that doesn't exist in TARGETS errors and exits 1."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit):
        deploytool.lib.resolve(["casino.nonexistent"], with_deps=False)
    out = "\n".join(msgs)
    assert "nonexistent" in out
    assert "tui" in out
    assert "www" in out


# ---------------------------------------------------------------------------
# CLI parser: --with-deps defaults to False and round-trips
# ---------------------------------------------------------------------------


def test_buildargs_with_deps_defaults_to_false():
    """Without --with-deps, args.with_deps is False."""
    args = deploytool.lib.buildargs().parse_args(["casino.tui"])
    assert args.with_deps is False


def test_buildargs_with_deps_sets_flag():
    """--with-deps sets args.with_deps = True."""
    args = deploytool.lib.buildargs().parse_args(
        ["--with-deps", "casino.tui"]
    )
    assert args.with_deps is True


def test_buildargs_with_deps_compatible_with_editable():
    """--with-deps and --editable round-trip together."""
    args = deploytool.lib.buildargs().parse_args(
        ["--with-deps", "--editable", "casino.tui"]
    )
    assert args.with_deps is True
    assert args.editable is True


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
