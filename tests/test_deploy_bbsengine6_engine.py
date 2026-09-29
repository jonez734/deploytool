"""Tests for bbsengine6's engine stage/prod sub-targets.

bbsengine6 surfaces two new subs under deploytool that split the
engine entry-point PHP install on the zoidtechnologies.com vhost
into a local stage step and a merlin-push prod step:

  - `bbsengine6.engine-stage` — `make deploy-engine-stage` →
                               `make -C engine stage`, which
                               rsyncs `bbsengine6/engine/*.php`
                               to
                               `/srv/www/vhosts/zoidtechnologies.com/html/engine/`.
  - `bbsengine6.engine-prod`  — `make deploy-engine-prod` →
                               `make engine-deploy-prod` (the
                               existing umbrella at
                               `bbsengine6/Makefile:220-221`),
                               which in turn calls
                               `make -C engine deploy` (stage +
                               merlin push).

Both wrappers rely on the existing defaults at
`bbsengine6/Makefile:22-23` and `bbsengine6/engine/Makefile:2-3`
(ENGINESTAGEDOCROOT = zoidtechnologies.com,
ENGINEPRODDOCROOT = $(ENGINEHOST):$(ENGINESTAGEDOCROOT),
ENGINEHOST = merlin). No per-vhost override is needed for the
zoidtechnologies.com vhost.

These subs coexist with the existing `bbsengine6.wwworg` recipe,
which uses inline overrides to point the same machinery at the
bbsengine.org vhost. The two recipes are independent: wwworg
handles its own vhost, engine-prod handles the default vhost.

The bare prefix `engine` is ambiguous because both subs start
with `engine`; callers must name `engine-stage` or `engine-prod`
in full. The shorter prefixes `engine-s` and `engine-p` are
uniquely resolvable.

These tests are the deploy-side counterpart to the bbsengine6
Makefile changes that introduced `deploy-engine-stage` and
`deploy-engine-prod`. They guard against regressions where
someone removes one of the subs (silently reverting to a smaller
TARGETS), breaks the make-rule wiring on the bbsengine6 side, or
removes the underlying `stage` / `deploy-engine` targets in
`bbsengine6/engine/Makefile`.
"""

import argparse
import re
from pathlib import Path

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# TARGETS shape
# ---------------------------------------------------------------------------


def test_bbsengine6_targets_includes_engine_stage_and_engine_prod():
    """bbsengine6 TARGETS must end with the engine stage/prod pair.

    The exact-list assertion lives in
    `test_deploy_bbsengine6_www.py::test_bbsengine6_targets_has_eight_subs`
    so the full shape is pinned there. This test focuses on the
    new entries: their presence at the tail of the list, in the
    documented order, with no duplicate or shadow.
    """
    targets = deploytool.lib.get_targets("bbsengine6")
    assert "engine-stage" in targets, (
        f"engine-stage must be in bbsengine6 TARGETS; got {targets!r}"
    )
    assert "engine-prod" in targets, (
        f"engine-prod must be in bbsengine6 TARGETS; got {targets!r}"
    )
    assert targets.count("engine-stage") == 1
    assert targets.count("engine-prod") == 1
    assert targets[-2:] == ["engine-stage", "engine-prod"], (
        f"engine subs must be the trailing pair in TARGETS, in stage-then-prod order; "
        f"got tail {targets[-2:]!r} from {targets!r}"
    )


# ---------------------------------------------------------------------------
# Bare invocation: warn + exit (delegated to test_deploy_bbsengine6_www.py
# for the full eight-sub assertion; here we just confirm engine subs are
# reachable via the bare-base path).
# ---------------------------------------------------------------------------


def test_bare_bbsengine6_lists_engine_subs_in_ambiguity_message(monkeypatch):
    """`deploy bbsengine6` (bare) lists engine-stage and engine-prod
    in the ambiguity message so operators can discover them."""
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
        deploytool.lib.resolve(["bbsengine6"], with_deps=False)
    assert excinfo.value.code == 1

    out = "\n".join(msgs)
    assert "engine-stage" in out, "resolver must list engine-stage in the available subs"
    assert "engine-prod" in out, "resolver must list engine-prod in the available subs"


# ---------------------------------------------------------------------------
# Explicit sub resolution
# ---------------------------------------------------------------------------


def test_explicit_engine_stage_resolves_to_single_entry():
    """`deploy bbsengine6.engine-stage` -> [('bbsengine6', 'engine-stage')]."""
    order = deploytool.lib.resolve(["bbsengine6.engine-stage"], with_deps=False)
    assert order == [("bbsengine6", "engine-stage")]


def test_explicit_engine_prod_resolves_to_single_entry():
    """`deploy bbsengine6.engine-prod` -> [('bbsengine6', 'engine-prod')]."""
    order = deploytool.lib.resolve(["bbsengine6.engine-prod"], with_deps=False)
    assert order == [("bbsengine6", "engine-prod")]


def test_both_engine_subs_resolved_in_caller_order():
    """Caller-named subs keep their order; no auto-expansion."""
    order = deploytool.lib.resolve(
        ["bbsengine6.engine-stage", "bbsengine6.engine-prod"], with_deps=False
    )
    assert order == [("bbsengine6", "engine-stage"), ("bbsengine6", "engine-prod")]


# ---------------------------------------------------------------------------
# Shortest-unique-prefix resolution
# ---------------------------------------------------------------------------


def test_shortest_prefix_engine_s_resolves_to_engine_stage():
    """`deploy bbsengine6.engine-s` -> engine-stage (unique prefix)."""
    order = deploytool.lib.resolve(["bbsengine6.engine-s"], with_deps=False)
    assert order == [("bbsengine6", "engine-stage")]


def test_shortest_prefix_engine_p_resolves_to_engine_prod():
    """`deploy bbsengine6.engine-p` -> engine-prod (unique prefix)."""
    order = deploytool.lib.resolve(["bbsengine6.engine-p"], with_deps=False)
    assert order == [("bbsengine6", "engine-prod")]


def test_bare_engine_prefix_is_ambiguous(monkeypatch):
    """`deploy bbsengine6.engine` matches both engine-stage and
    engine-prod; resolver emits the distinct "ambiguous sub-target
    prefix" error and lists the matches."""
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
        deploytool.lib.resolve(["bbsengine6.engine"], with_deps=False)
    assert excinfo.value.code == 1

    out = "\n".join(msgs)
    assert "ambiguous" in out, "resolver must use the ambiguous-prefix error path"
    assert "engine-stage" in out, "ambiguous message must list engine-stage"
    assert "engine-prod" in out, "ambiguous message must list engine-prod"


def test_unknown_engine_sub_target_errors(monkeypatch):
    """`deploy bbsengine6.engine-foo` (not a real sub) is rejected
    with the available list."""
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
        deploytool.lib.resolve(["bbsengine6.engine-foo"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "engine-stage" in out
    assert "engine-prod" in out


# ---------------------------------------------------------------------------
# Makefile target wiring (mirror what's expected on the bbsengine6 side)
# ---------------------------------------------------------------------------


def test_make_target_for_engine_stage_is_deploy_engine_stage():
    """run_make_deploy must construct 'deploy-engine-stage' for
    bbsengine6.engine-stage."""
    project = "bbsengine6"
    sub = "engine-stage"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-engine-stage"


def test_make_target_for_engine_prod_is_deploy_engine_prod():
    """run_make_deploy must construct 'deploy-engine-prod' for
    bbsengine6.engine-prod."""
    project = "bbsengine6"
    sub = "engine-prod"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-engine-prod"


def test_bbsengine6_makefile_defines_deploy_engine_stage():
    """The bbsengine6 root Makefile must define a deploy-engine-stage target.

    Mirrors deploytool's "make target must exist" contract: if a
    TARGETS sub exists but no corresponding make rule, deploytool
    silently does the wrong thing (make fails with 'No rule to make
    target deploy-engine-stage' but the deploy itself exits 0 because
    the subprocess was caught). Guarding here means a regression
    surfaces in CI, not in production.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "deploy-engine-stage:" in text, (
        "bbsengine6/Makefile must define a deploy-engine-stage target. "
        f"Got:\n{text}"
    )


def test_bbsengine6_makefile_defines_deploy_engine_prod():
    """Same regression guard as test_bbsengine6_makefile_defines_deploy_engine_stage
    but for the prod wrapper."""
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "deploy-engine-prod:" in text, (
        "bbsengine6/Makefile must define a deploy-engine-prod target. "
        f"Got:\n{text}"
    )


def test_bbsengine6_makefile_lists_engine_targets_as_phony():
    """deploy-engine-stage and deploy-engine-prod must appear in the
    .PHONY list so `make` doesn't try to satisfy them with a same-named
    file in the working tree."""
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    phony_match = re.search(r"^\.PHONY:\s*(.+)$", text, re.MULTILINE)
    assert phony_match, "bbsengine6/Makefile must have a .PHONY: declaration"
    phony_line = phony_match.group(1)
    assert "deploy-engine-stage" in phony_line, (
        f"deploy-engine-stage must be in .PHONY; got: {phony_line!r}"
    )
    assert "deploy-engine-prod" in phony_line, (
        f"deploy-engine-prod must be in .PHONY; got: {phony_line!r}"
    )


def test_bbsengine6_makefile_engine_stage_delegates_to_engine_submake():
    """The deploy-engine-stage wrapper must delegate to a real engine
    sub-make call. Convention is `deploy-engine-stage: ; $(MAKE) -C
    engine stage`; without a `$(MAKE) -C engine stage` invocation the
    wrapper is a no-op.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert re.search(
        r"^deploy-engine-stage:.*\n\s+\$\(MAKE\)\s+-C\s+engine\s+stage",
        text,
        re.MULTILINE,
    ), (
        "bbsengine6/Makefile deploy-engine-stage wrapper must delegate to "
        "`$(MAKE) -C engine stage`."
    )


def test_bbsengine6_makefile_engine_prod_delegates_to_engine_deploy_prod():
    """The deploy-engine-prod wrapper must delegate to the existing
    engine-deploy-prod umbrella (which itself does stage + merlin push).
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert re.search(
        r"^deploy-engine-prod:.*\n\s+\$\(MAKE\)\s+engine-deploy-prod",
        text,
        re.MULTILINE,
    ), (
        "bbsengine6/Makefile deploy-engine-prod wrapper must delegate to "
        "`$(MAKE) engine-deploy-prod`."
    )


# ---------------------------------------------------------------------------
# Underlying engine/Makefile shape (the wrappers point at these targets)
# ---------------------------------------------------------------------------


def test_engine_makefile_has_stage_target():
    """bbsengine6/engine/Makefile must define the `stage` target that
    deploy-engine-stage ultimately invokes. Without it, the wrapper
    fails with 'No rule to make target stage'."""
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "engine" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert re.search(r"^stage:", text, re.MULTILINE), (
        "bbsengine6/engine/Makefile must define a `stage:` target. "
        f"Got:\n{text}"
    )


def test_engine_makefile_has_deploy_engine_target():
    """bbsengine6/engine/Makefile must define the `deploy-engine`
    target that the engine-deploy-prod umbrella calls. Without it,
    the prod push fails."""
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "engine" / "Makefile"
    text = makefile.read_text()
    assert re.search(r"^deploy-engine:", text, re.MULTILINE), (
        "bbsengine6/engine/Makefile must define a `deploy-engine:` target. "
        f"Got:\n{text}"
    )


def test_engine_makefile_default_docroot_points_to_zoidtechnologies():
    """The `?=` default ENGINESTAGEDOCROOT in bbsengine6/engine/Makefile
    must point at the zoidtechnologies.com vhost so the new
    engine-stage / engine-prod subs land on the right vhost without
    needing per-vhost overrides.

    Mirrors the same `?=` default at bbsengine6/Makefile:22 which the
    parent Makefile also relies on.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "engine" / "Makefile"
    text = makefile.read_text()
    assert "/srv/www/vhosts/zoidtechnologies.com/html/engine/" in text, (
        "bbsengine6/engine/Makefile must default ENGINESTAGEDOCROOT to "
        "/srv/www/vhosts/zoidtechnologies.com/html/engine/ so the new "
        "engine-stage / engine-prod subs land on the right vhost."
    )


# ---------------------------------------------------------------------------
# ENGINE_DOCROOT env-var override (per-vhost /engine/ install)
# ---------------------------------------------------------------------------


def test_engine_makefile_honors_engine_docroot_env_var():
    """bbsengine6/engine/Makefile must read ENGINE_DOCROOT as the new
    default for ENGINESTAGEDOCROOT.

    Two assertions pin the contract:

      - `ENGINE_DOCROOT ?=` is declared (so unset env var falls through
        to the zoidtechnologies.com default).
      - `ENGINESTAGEDOCROOT ?= $(ENGINE_DOCROOT)` chains the existing
        variable to the new one. Without this, callers who override
        only ENGINE_DOCROOT still get the zoidtechnologies.com path
        because the engine sub-make's `stage:` and `deploy:` rules read
        `$(ENGINESTAGEDOCROOT)`, not `$(ENGINE_DOCROOT)` directly.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "engine" / "Makefile"
    text = makefile.read_text()
    assert re.search(
        r"^ENGINE_DOCROOT\s*\?=", text, re.MULTILINE
    ), "bbsengine6/engine/Makefile must declare `ENGINE_DOCROOT ?=`."
    assert re.search(
        r"^ENGINESTAGEDOCROOT\s*\?=\s*\$\(ENGINE_DOCROOT\)", text, re.MULTILINE
    ), (
        "bbsengine6/engine/Makefile must chain `ENGINESTAGEDOCROOT ?= "
        "$(ENGINE_DOCROOT)` so the env var override propagates to the "
        "stage / deploy rules."
    )


def test_parent_makefile_honors_engine_docroot_env_var():
    """bbsengine6/Makefile (parent) must also read ENGINE_DOCROOT and
    export it, so recipes at this layer that consume $(ENGINESTAGEDOCROOT)
    — `wwworg:`, `prod:`, the bare `deploy:` umbrella — inherit the
    env-var override without each call site needing its own plumbing.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert re.search(
        r"^export\s+ENGINE_DOCROOT\s*\?=", text, re.MULTILINE
    ), "bbsengine6/Makefile must `export ENGINE_DOCROOT ?=` so sub-makes inherit it."
    assert re.search(
        r"^export\s+ENGINESTAGEDOCROOT\s*\?=\s*\$\(ENGINE_DOCROOT\)",
        text,
        re.MULTILINE,
    ), (
        "bbsengine6/Makefile must chain `export ENGINESTAGEDOCROOT ?= "
        "$(ENGINE_DOCROOT)` so the env var override propagates to "
        "recipes at the parent layer."
    )


def test_wwworg_inline_engine_docroot_override_still_wins():
    """The existing `wwworg:` recipe's inline `ENGINESTAGEDOCROOT=...`
    override at bbsengine6/Makefile:135-136 must still point at the
    bbsengine.org vhost. Make's command-line > environment > file
    precedence is what protects this — the env var ENGINE_DOCROOT only
    takes effect when no inline override is present. This is a
    regression guard for the existing wwworg recipe shape.
    """
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert "ENGINESTAGEDOCROOT=/srv/www/vhosts/www.bbsengine.org/html/engine/" in text, (
        "bbsengine6/Makefile wwworg recipe must keep its inline "
        "ENGINESTAGEDOCROOT override pointing at the bbsengine.org vhost."
    )
    assert "ENGINEPRODDOCROOT=$(ORGHOST):/srv/www/vhosts/www.bbsengine.org/html/engine/" in text, (
        "bbsengine6/Makefile wwworg recipe must keep its inline "
        "ENGINEPRODDOCROOT override pointing at the bbsengine.org vhost."
    )


# ---------------------------------------------------------------------------
# run_make_deploy — ENGINE_DOCROOT env-var plumbing
# ---------------------------------------------------------------------------


def _make_args(projects, **overrides):
    """Build a Namespace matching the shape lib.run_make_deploy reads.

    Mirrors the helper in tests/test_deploy_upgrade.py so the
    ENGINE_DOCROOT plumbing tests look identical to the existing
    DEPLOY_EDITABLE / DEPLOY_WITH_DEPS / DEPLOY_UPGRADE patterns.
    """
    defaults = dict(
        projects=projects,
        host="merlin",
        dry_run=False,
        verify=False,
        editable=False,
        with_deps=False,
        upgrade=True,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _completed(returncode=0, stdout="", stderr=""):
    import types

    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_make_deploy_engine_docroot_set_in_environ_flows_to_subprocess_for_engine_stage(monkeypatch):
    """When ENGINE_DOCROOT is in os.environ, run_make_deploy passes it
    through to the make subprocess env for bbsengine6.engine-stage.

    Mirrors the DEPLOY_EDITABLE / DEPLOY_WITH_DEPS / DEPLOY_UPGRADE
    set-on-inherit contract. The ?= default in bbsengine6/engine/Makefile
    resolves to the operator's value, redirecting the rsync to the
    chosen vhost.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("ENGINE_DOCROOT", raising=False)
    monkeypatch.setenv("ENGINE_DOCROOT", "/srv/www/vhosts/foo.example.com/html/engine/")

    args = _make_args(["bbsengine6.engine-stage"])
    assert deploytool.lib.run_make_deploy(args, "bbsengine6", "engine-stage") == 0

    assert captured["env"].get("ENGINE_DOCROOT") == "/srv/www/vhosts/foo.example.com/html/engine/"
    assert captured["cmd"][:3] == [
        "make",
        "-C",
        f"{deploytool.lib.SOURCE_BASE}/bbsengine6",
    ]
    assert captured["cmd"][3] == "deploy-engine-stage"


def test_run_make_deploy_engine_docroot_set_in_environ_flows_to_subprocess_for_engine_prod(monkeypatch):
    """When ENGINE_DOCROOT is in os.environ, run_make_deploy passes it
    through to the make subprocess env for bbsengine6.engine-prod as
    well — so the stage and push land on the same vhost.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("ENGINE_DOCROOT", raising=False)
    monkeypatch.setenv("ENGINE_DOCROOT", "/srv/www/vhosts/bar.example.com/html/engine/")

    args = _make_args(["bbsengine6.engine-prod"])
    assert deploytool.lib.run_make_deploy(args, "bbsengine6", "engine-prod") == 0

    assert captured["env"].get("ENGINE_DOCROOT") == "/srv/www/vhosts/bar.example.com/html/engine/"
    assert captured["cmd"][3] == "deploy-engine-prod"


def test_run_make_deploy_engine_docroot_unset_does_not_set_env_var(monkeypatch):
    """When ENGINE_DOCROOT is NOT in os.environ, run_make_deploy strips
    it from the subprocess env. Mirrors the DEPLOY_EDITABLE /
    DEPLOY_WITH_DEPS / DEPLOY_UPGRADE strip-on-inherit pattern so a
    stale shell var can't silently redirect /engine/ to a wrong vhost.

    Note: ENGINE_DOCROOT has no CLI flag (env var only, like the other
    `DEPLOY_*` vars). There is no "strip on `--no-engine-docroot`"
    branch because there is no flag to flip -- the only way to set
    ENGINE_DOCROOT is to put it in the operator's shell env, and the
    strip-on-inherit guard covers the case where the var was set in
    some unrelated prior session and the current invocation does not
    want it.
    """
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _completed(returncode=0)

    monkeypatch.setattr(deploytool.lib.subprocess, "run", fake_run)
    monkeypatch.delenv("ENGINE_DOCROOT", raising=False)

    args = _make_args(["bbsengine6.engine-stage"])
    deploytool.lib.run_make_deploy(args, "bbsengine6", "engine-stage")

    assert "ENGINE_DOCROOT" not in captured["env"]

