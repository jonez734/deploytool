"""Tests for the `--with-deps` flag and bare-base ambiguity behavior.

Bare-base rules (see `lib.resolve` docstring and SPECS.md §4):

- A bare base with `TARGETS` containing multiple subs is ambiguous —
  regardless of `--with-deps`. `lib.resolve()` calls `sys.exit(1)`
  with the available subs listed. Caller must name at least one sub.
- A bare base with `TARGETS` containing exactly one sub auto-picks that
  sub (no choice to make).
- A bare base with no `TARGETS` (e.g. `getdate_next`'s alias
  `mistermcfeely`) has nothing to choose from; the bare `make deploy`
  target runs.

The `--with-deps` flag controls dep walking independently and does
NOT change bare-base behavior:

- `with_deps=False` (default): no transitive deps are pulled in.
  Only the projects the caller named run.
- `with_deps=True`: the topo-sorted dep chain runs for each requested
  project. `--with-deps` is orthogonal to `--editable`. Bare-base
  invocation under `--with-deps` is still ambiguous when
  `len(TARGETS[foo]) > 1`.
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


def test_bare_casino_with_deps_is_ambiguous(monkeypatch):
    """`deploy --with-deps casino` (bare) is ambiguous: list subs + exit 1.

    `--with-deps` controls dep walking, not sub-target expansion.
    Bare-base invocation under `--with-deps` is still ambiguous when
    `TARGETS[casino]` has more than one entry. Caller must name the
    subs explicitly (`deploy --with-deps casino.tui casino.www`).
    """
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["casino"], with_deps=True)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "casino" in out
    assert "tui" in out
    assert "www" in out


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
    """Projects with no TARGETS run bare `make deploy` (no ambiguity possible).

    Note: mistermcfeely was bare-base at this test's origin but
    migrated to TARGETS=['tui','prod'] (see deploytool/CHANGELOG.md
    Unreleased / Changed). Pick another bare-base project for the
    negative-control assertion — `asimov` is the canonical
    remaining bare-base example.
    """
    order = deploytool.lib.resolve(["asimov"], with_deps=False)
    assert order == [("asimov", None)]


def test_bare_mistermcfeely_is_ambiguous_with_subs():
    """`deploy mistermcfeely` (bare) is now ambiguous after mistermcfeely
    was added to TARGETS=['tui','prod']. The resolver exits 1 listing
    the available subs. Mirrors the bed/zoid6 multi-sub pattern.
    """
    with pytest.raises(SystemExit):
        deploytool.lib.resolve(["mistermcfeely"], with_deps=False)


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


def test_with_deps_explicit_casino_subs_walks_full_chain():
    """`deploy --with-deps casino.tui casino.www` walks the chain for both.

    The previous "auto-expand all subs under --with-deps" shortcut is
    gone; callers name the subs explicitly to get the full chain for
    each. Both subs' chains merge into one topo-sorted order.
    """
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


def test_with_deps_bare_bed_is_ambiguous(monkeypatch):
    """`deploy --with-deps bed` (bare) is ambiguous regardless of --with-deps.

    bed has three subs (`tui`, `venv`, `prod`); bare invocation under
    any flag set is ambiguous. The resolver lists all three and exits 1.
    """
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["bed"], with_deps=True)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "bed" in out
    assert "tui" in out
    assert "venv" in out
    assert "prod" in out


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


# ---------------------------------------------------------------------------
# DEPLOY_WITH_DEPS env-var plumbing (lib.run_make_deploy)
#
# `--with-deps` is plumbed into the subprocess env as `DEPLOY_WITH_DEPS=1`
# so per-project Makefiles (specifically bbsengine6/py/src/Makefile
# precheck-editable) can opt into a less-strict precondition check.
# Mirrors the DEPLOY_EDITABLE env-var pattern; follows the same
# single-source-of-truth contract (set when CLI flag is passed, strip
# from inherited env when not, so a stray shell var can't accidentally
# flip a Makefile out of its default branch).
#
# End-to-end pinning of the contract this env var supports (precheck
# hard-fail vs. warn-and-proceed, and the verify-install catch when
# the editable .pth finder actually shadows the wheel install) lives
# in tests/test_deploy_shadow_install.py.
# ---------------------------------------------------------------------------

import subprocess as _std_subprocess
import types as _types
from argparse import Namespace as _Namespace


def _make_args(projects, **overrides):
    """Build a Namespace matching the shape lib.run_make_deploy reads."""
    defaults = dict(
        projects=projects,
        host="merlin",
        dry_run=False,
        verify=False,
        editable=False,
        with_deps=False,
    )
    defaults.update(overrides)
    return _Namespace(**defaults)


def _completed(returncode=0, stdout="", stderr=""):
    return _types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_make_deploy_with_deps_sets_env_var(monkeypatch):
    """--with-deps plumbs DEPLOY_WITH_DEPS=1 into the subprocess env."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    args = _make_args(["bbsengine6.tui"], with_deps=True)
    assert deploytool.lib.run_make_deploy(args, "bbsengine6", "tui") == 0

    assert captured["env"].get("DEPLOY_WITH_DEPS") == "1"
    # Sanity-check: also covers the canonical with_deps sub-target name
    # flowing through the make command vector.
    assert captured["cmd"][:3] == ["make", "-C", f"{deploytool.lib.SOURCE_BASE}/bbsengine6"]


def test_run_make_deploy_without_with_deps_strips_env_var(monkeypatch):
    """Without --with-deps, a stray DEPLOY_WITH_DEPS=1 in the operator's
    shell is stripped so the per-project Makefile falls back to its
    default branch. Mirrors the DEPLOY_EDITABLE strip-on-inherit
    contract documented in SPECS.md §2.1."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_WITH_DEPS", raising=False)
    monkeypatch.setenv("DEPLOY_WITH_DEPS", "1")

    args = _make_args(["bbsengine6.tui"], with_deps=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert "DEPLOY_WITH_DEPS" not in captured["env"]


def test_run_make_deploy_with_deps_does_not_touch_editable_strip(monkeypatch):
    """--with-deps and --editable are orthogonal; passing --with-deps
    alone must still strip DEPLOY_EDITABLE so an operator with a stale
    DEPLOY_EDITABLE=1 in their shell doesn't accidentally flip into
    editable install mode."""
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs["env"]
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("DEPLOY_EDITABLE", raising=False)
    monkeypatch.setenv("DEPLOY_EDITABLE", "1")

    args = _make_args(["bbsengine6.tui"], with_deps=True, editable=False)
    deploytool.lib.run_make_deploy(args, "bbsengine6", "tui")
    assert captured["env"].get("DEPLOY_WITH_DEPS") == "1"
    assert "DEPLOY_EDITABLE" not in captured["env"]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
