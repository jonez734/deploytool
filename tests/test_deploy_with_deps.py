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

    casino.www's CONDITIONAL_DEPENDENCIES edge was previously
    `("bbsengine6", "www")` — a legacy entry that emitted a
    `('bbsengine6', 'www')` edge and silently tried to run
    `make -C bbsengine6 deploy-www`, which doesn't exist (the `www`
    sub was removed in 2025). The edge is now `("bbsengine6", "prod")`
    so the chain lands the engine-library umbrella correctly.
    """
    order = deploytool.lib.resolve(
        ["casino.tui", "casino.www"], with_deps=True
    )
    assert order == [
        ("bbsengine6", "prod"),
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
    """`deploy --with-deps casino.tui casino.www` merges chains.

    casino.www's CONDITIONAL_DEPENDENCIES edge was previously
    `("bbsengine6", "www")` (broken: the legacy `www` sub was
    removed); now `("bbsengine6", "prod")` (the new engine-library
    umbrella sub). See the comment on
    `test_with_deps_explicit_casino_subs_walks_full_chain` for the
    full rationale.
    """
    order = deploytool.lib.resolve(
        ["casino.tui", "casino.www"], with_deps=True
    )
    assert order == [
        ("bbsengine6", "prod"),
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
# Conditional deps — `te.www` walks `("zoid6", "shared")` first
# (https://github.com/jonez734/deploytool@2026-09-27)
# ---------------------------------------------------------------------------


def test_teos_www_with_deps_walks_bbsengine6_prod_first():
    """`deploy --with-deps teos.www` runs bbsengine6.prod before teos.www.

    The teos vhost rsync (the `deploy-www:` rule at teos/Makefile:30)
    depends on bbsengine6's engine-library install — teos renders
    through `bbsengine6/engine/*.php` (router.php, serve-md.php,
    join.php, login.php, logout.php) plus bbsengine6's `php/` library
    and `skin/tmpl/` chrome. The library must land on merlin before
    the teos vhost tree ships, otherwise a curl-grep on a freshly
    deployed teos URL sees new teos config but old/stale engine
    binaries.

    Prior to 2026-09-29 this chain relied on DEPENDENCIES['teos'] =
    ['bbsengine6', 'zoid6'] walking bare-base bbsengine6 (which
    silently emitted ('bbsengine6', None) and ran `make -C bbsengine6
    deploy` — the engine-library umbrella). The new explicit edge
    `("bbsengine6", "prod")` in CONDITIONAL_DEPENDENCIES['teos']['www']
    makes the chain self-documenting and replaces the accidental
    bare-base behavior.
    """
    order = deploytool.lib.resolve(["teos.www"], with_deps=True)
    assert ("bbsengine6", "prod") in order, (
        f"('bbsengine6', 'prod') must be in the teos.www --with-deps chain; "
        f"got {order!r}. The CONDITIONAL_DEPENDENCIES['teos']['www'] entry "
        f"is what pulls it in."
    )
    assert ("teos", "www") in order
    assert order.index(("bbsengine6", "prod")) < order.index(("teos", "www")), (
        f"('bbsengine6', 'prod') must run before ('teos', 'www'); got {order!r}. "
        f"The engine-library install must land before teos's vhost rsync."
    )


def test_teos_www_with_deps_walks_zoid6_shared_first():
    """`deploy --with-deps teos.www` runs zoid6.shared before teos.www.

    teos renders through zoid6/shared/skin/tmpl/page.tmpl, so the
    shared template must land on the target host before teos's
    vhost config. Otherwise a curl probe after a single deploy can
    see the new config but the old shared template (or vice versa).
    """
    order = deploytool.lib.resolve(["teos.www"], with_deps=True)
    assert ("zoid6", "shared") in order
    assert ("teos", "www") in order
    assert order.index(("zoid6", "shared")) < order.index(("teos", "www")), (
        f"zoid6.shared must run before teos.www; got {order!r}"
    )


def test_teos_www_with_deps_walks_teos_engine_before_teos_www():
    """`deploy --with-deps teos.www` runs `("teos", "engine")` before `("teos", "www")`.

    The `engine` sub (which delegates to bbsengine6's
    engine-deploy-prod umbrella) re-stages and re-pushes the
    zoidtechnologies.com/html/engine/ install — the entry-point PHP
    files teos renders through. It must land before teos's own vhost
    rsync so the engine install is fresh by the time teos.www ships
    the surrounding vhost tree. Mirrors the test above (zoid6.shared
    before teos.www) — both CONDITIONAL_DEPENDENCIES entries are
    consulted under --with-deps.
    """
    order = deploytool.lib.resolve(["teos.www"], with_deps=True)
    assert ("teos", "engine") in order, (
        f"('teos', 'engine') must be in the teos.www --with-deps chain; "
        f"got {order!r}. The CONDITIONAL_DEPENDENCIES['teos']['www'] entry "
        f"is what pulls it in."
    )
    assert ("teos", "www") in order
    assert order.index(("teos", "engine")) < order.index(("teos", "www")), (
        f"('teos', 'engine') must run before ('teos', 'www'); got {order!r}. "
        f"The engine install must land before teos's own vhost rsync."
    )


def test_teos_www_without_with_deps_does_not_walk_zoid6_shared():
    """`deploy teos.www` (no --with-deps) does NOT auto-include zoid6.shared.

    The CONDITIONAL_DEPENDENCIES entry is only consulted under
    --with-deps. The bare `deploy teos.www` invocation stays a
    single-step deploy so callers who don't want shared pushed
    keep that opt-out.
    """
    order = deploytool.lib.resolve(["teos.www"], with_deps=False)
    assert order == [("teos", "www")]


def test_teos_prod_with_deps_walks_full_chain():
    """`deploy --with-deps teos.prod` walks bbsengine6.prod ->
    zoid6.shared -> teos.engine -> teos.prod in that order.

    `teos.prod` is the single-command surface for "stage and install
    everything required for teos" — the bbsengine6 engine library
    (php + engine + skin + smarty), the zoid6 shared chrome, the
    zoidtechnologies.com/html/engine/ install, and the teos vhost
    itself. The chain walks in topo order: engine library first
    (it has no deps), shared chrome second (it depends on zoid6
    being up-to-date), engine install third (it depends on the
    engine library being staged), and teos.prod last (it depends on
    everything above being live on merlin).
    """
    order = deploytool.lib.resolve(["teos.prod"], with_deps=True)
    assert order == [
        ("bbsengine6", "prod"),
        ("zoid6", "shared"),
        ("teos", "engine"),
        ("teos", "prod"),
    ], (
        f"deploy --with-deps teos.prod must walk the full chain in "
        f"this exact topo order; got {order!r}. See "
        f"CONDITIONAL_DEPENDENCIES['teos']['prod'] for the source of truth."
    )


def test_teos_prod_with_deps_matches_teos_www_chain():
    """`deploy --with-deps teos.prod` and `deploy --with-deps teos.www`
    produce identical topo chains except for the trailing sub.

    Both subs alias to the same make target (`deploy-www:` at
    teos/Makefile:30 via MAKE_TARGET_ALIASES), so the chain shape
    is intentionally the same — the user-facing difference is
    intent: `www` says "deploy the teos vhost"; `prod` says "deploy
    the whole teos stack". Today they produce the same order; future
    evolution could split them if teos gains a vhost-only deploy.
    """
    www_order = deploytool.lib.resolve(["teos.www"], with_deps=True)
    prod_order = deploytool.lib.resolve(["teos.prod"], with_deps=True)
    assert www_order[:-1] == prod_order[:-1], (
        f"teos.www and teos.prod chains must match except for the "
        f"trailing sub; got www={www_order!r} prod={prod_order!r}"
    )
    assert www_order[-1] == ("teos", "www")
    assert prod_order[-1] == ("teos", "prod")


def test_teos_prod_without_with_deps_does_not_walk_chain():
    """`deploy teos.prod` (no --with-deps) is a single-step deploy.

    Mirrors `test_teos_www_without_with_deps_does_not_walk_zoid6_shared`
    for the new `prod` sub. The CONDITIONAL_DEPENDENCIES entries are
    only consulted under --with-deps so the bare sub stays a
    one-step deploy (callers who don't want the engine-library
    umbrella / shared chrome pushed keep that opt-out).
    """
    order = deploytool.lib.resolve(["teos.prod"], with_deps=False)
    assert order == [("teos", "prod")]


def test_teos_tui_with_deps_does_not_walk_zoid6_shared():
    """te.tui does not depend on zoid6.shared.

    The TUI bundles its own chrome and renders Smarty templates
    client-side, not through the shared/skin/tmpl/page.tmpl
    hierarchy. Pulling in zoid6.shared for the TUI would be a
    no-op deploy at best, and confusing at worst. (Bare deps
    bbsengine6 and zoid6 still walk under --with-deps; the
    assertion is that zoid6.shared specifically does NOT appear.)
    """
    order = deploytool.lib.resolve(["teos.tui"], with_deps=True)
    assert ("zoid6", "shared") not in order, (
        f"te.tui must not pull in zoid6.shared; got {order!r}"
    )
    assert order[-1] == ("teos", "tui")


def test_zoid6_shared_subtarget_is_registered_and_resolves_to_canonical_name():
    """`zoid6.shared` is a registered sub-target and resolves without ambiguity.

    The resolver must accept `zoid6.shared` and produce a single
    (zoid6, shared) entry. Short-prefix matching (e.g.
    `zoid6.s`) must NOT match another sub in the zoid6 TARGETS
    list, so `shared` is the canonical name.
    """
    targets = deploytool.lib.get_targets("zoid6")
    assert "shared" in targets, "zoid6 must declare 'shared' as a deployable sub"
    resolved = deploytool.lib.resolve(["zoid6.shared"], with_deps=False)
    assert resolved == [("zoid6", "shared")]
    # Short-prefix matching: only one zoid6 sub starts with "s"
    # (the new 'shared' entry; www/tui/prod all start with other
    # letters). Confirm `zoid6.s` resolves to `shared` and not
    # any other sub.
    resolved_short = deploytool.lib.resolve(["zoid6.s"], with_deps=False)
    assert resolved_short == [("zoid6", "shared")]


def test_zoid6_shared_make_target_aliases_to_bare_shared():
    """`deploy zoid6.shared` runs `make -C zoid6 shared`, not `make deploy-shared`.

    zoid6's Makefile declares the target as `shared:` (no
    `deploy-` prefix). The MAKE_TARGET_ALIASES table maps the
    user-facing sub name to the actual make target name.
    """
    assert deploytool.lib.MAKE_TARGET_ALIASES.get(("zoid6", "shared")) == "shared"


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
