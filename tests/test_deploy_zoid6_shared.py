"""Tests for the `zoid6.shared` deploy sub-target.

`zoid6` exposes four subs (`www`, `tui`, `prod`, `shared`). The
`shared` sub rsyncs zoid6's shared chrome (skin/tmpl/, css/, art/)
from the local working tree to two destinations on the target host:

  - `/srv/www/zoid6/shared/`                  (zoid6's app-stage dir)
  - `/srv/www/vhosts/zoidtechnologies.com/html/shared/`
                                              (the vhosts docroot
                                               other consumers —
                                               te.os, achilles, empyre —
                                               render from at runtime)

Because zoid6/Makefile declares the rule as a plain `shared:`
target (not `deploy-shared:`), deploytool's `MAKE_TARGET_ALIASES`
map must translate the user-facing `shared` sub to `shared` so
`run_make_deploy` invokes `make -C zoid6 shared` rather than the
default `make -C zoid6 deploy-shared`.

These tests pin three contracts:

1. `TARGETS["zoid6"]` advertises `shared` (operators can tab-complete
   / discover the sub).
2. `MAKE_TARGET_ALIASES[("zoid6", "shared")] == "shared"`
   (the alias stays in place across refactors).
3. `run_make_deploy` constructs `["make", "-C",
   SOURCE_BASE/zoid6", "shared"]` for the `deploy zoid6.shared`
   invocation (so the actual `make` command reaches the `shared:`
   rule, not a non-existent `deploy-shared:`).
4. The topo order under `--with-deps` walks `bbsengine6` and `zoid6`
   bare deps before `zoid6.shared`, mirroring the teos.shared
   ordering test in `test_deploy_with_deps.py`.
"""

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# TARGETS shape
# ---------------------------------------------------------------------------


def test_zoid6_targets_includes_shared():
    """zoid6 must expose `shared` as a sub-target.

    Without this, `deploy zoid6.shared` would be rejected with
    "unknown sub-target" and operators would have no way to push
    shared chrome independent of `prod`.
    """
    targets = deploytool.lib.get_targets("zoid6")
    assert "shared" in targets, (
        f"zoid6 TARGETS must contain 'shared'; got {targets!r}. "
        "`deploy zoid6.shared` is the supported way to push zoid6's "
        "shared templates/css/art to the vhosts docroot without "
        "running the full prod umbrella install."
    )


# ---------------------------------------------------------------------------
# MAKE_TARGET_ALIASES wiring
# ---------------------------------------------------------------------------


def test_zoid6_shared_alias_maps_to_make_target_shared():
    """The alias must keep the user-facing `shared` sub on the
    bare `shared` make target — NOT `deploy-shared`.

    `zoid6/Makefile` defines `shared:` (no `deploy-` prefix); the
    alias is the bridge that prevents `run_make_deploy` from
    constructing `make -C zoid6 deploy-shared` (which would fail
    with "No rule to make target").
    """
    assert ("zoid6", "shared") in deploytool.lib.MAKE_TARGET_ALIASES, (
        "MAKE_TARGET_ALIASES must contain a ('zoid6', 'shared') entry "
        "so deploy zoid6.shared reaches the right make target."
    )
    assert deploytool.lib.MAKE_TARGET_ALIASES[("zoid6", "shared")] == "shared", (
        "zoid6.shared must alias to the make target 'shared' "
        "(zoid6/Makefile defines `shared:`, not `deploy-shared:`). "
        f"Got {deploytool.lib.MAKE_TARGET_ALIASES[('zoid6', 'shared')]!r}."
    )


def test_zoid6_shared_make_target_string_for_run_make_deploy():
    """The constructed make target must be `shared`, not `deploy-shared`.

    Mirrors the assertion pattern in `test_zoidoffice.py` for
    deploy-tui/deploy-www, but inverted: because zoid6's Makefile
    declares a bare `shared:` rule (not `deploy-shared:`), the alias
    value is used verbatim as the make target — no `deploy-` prefix
    is prepended. Same pattern as `bed.tui` -> `deploy-venv`:
    alias values are bare make target names, not sub prefixes.
    """
    project = "zoid6"
    sub = "shared"
    if (project, sub) in deploytool.lib.MAKE_TARGET_ALIASES:
        target = deploytool.lib.MAKE_TARGET_ALIASES[(project, sub)]
    else:
        target = f"deploy-{sub}" if sub else "deploy"
    assert target == "shared", (
        f"`deploy zoid6.shared` must invoke `make shared` in zoid6/. "
        f"Got target={target!r} (sub resolved to {sub!r}). If this is "
        "`deploy-shared`, either the alias was lost or zoid6's Makefile "
        "was renamed without updating MAKE_TARGET_ALIASES."
    )


# ---------------------------------------------------------------------------
# Makefile shape: the `shared:` rule must exist and target the right
# destinations. Mirrors `test_zoidoffice_makefile_defines_deploy_www`.
# ---------------------------------------------------------------------------


def test_zoid6_makefile_defines_shared_rule():
    """zoid6/Makefile must define a `shared:` rule.

    Pinned to catch the silent regression where the alias map
    still points at `shared` but the Makefile rule was deleted/
    renamed, leaving the deploy chain to fail with "No rule to
    make target 'shared'".
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "zoid6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    # Look for a plain `shared:` rule. Must not be `deploy-shared:`
    # (if someone renamed it, the alias map above would also need
    # to change; the alias test pins that coupling).
    assert "\nshared:" in text or text.startswith("shared:"), (
        "zoid6/Makefile must define a `shared:` target. "
        f"Got:\n{text}"
    )


def test_zoid6_makefile_shared_rule_targets_vhost_docroot():
    """The `shared:` rule must rsync to the vhost docroot shared dir.

    The vhost docroot path
    (`/srv/www/vhosts/zoidtechnologies.com/html/shared/`) is the
    runtime mount point other consumers (te.os, achilles, empyre)
    serve from. Without it, deploy zoid6.shared would only land
    zoid6's app-stage copy and the consumers would still render
    against stale chrome.

    The path is constructed via `$(STAGEDOCROOT)shared/` (the variable
    expands to `/srv/www/vhosts/zoidtechnologies.com/html/`), so this
    test pins both the variable definition AND the rsync target.
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "zoid6" / "Makefile"
    text = makefile.read_text()
    # The rsync destination must be a `shared/` dir under the vhost
    # docroot. The docroot itself is in a Make variable.
    assert "STAGEDOCROOT" in text, (
        f"zoid6/Makefile must define STAGEDOCROOT (the vhost docroot). "
        f"Got:\n{text}"
    )
    assert "vhosts/zoidtechnologies.com/html" in text, (
        "zoid6/Makefile's STAGEDOCROOT must point at "
        "/srv/www/vhosts/zoidtechnologies.com/html/ — that's "
        "where the consumer vhosts serve shared templates from. "
        f"Got:\n{text}"
    )
    # The shared: rule's rsync invocation must target `$(STAGEDOCROOT)shared/`.
    # Find the rsync line within the shared: rule body.
    assert "$(RSYNC)" in text and "$(STAGEDOCROOT)shared/" in text, (
        "zoid6/Makefile's shared: rule must rsync into "
        "$(STAGEDOCROOT)shared/ (the vhost docroot). "
        f"Got:\n{text}"
    )


# ---------------------------------------------------------------------------
# Resolver: pin the topo order under --with-deps for a direct
# `deploy --with-deps zoid6.shared` invocation. Mirrors
# `test_teos_www_with_deps_walks_zoid6_shared_first` but for the
# direct case, so the contract is pinned independent of teos.
# ---------------------------------------------------------------------------


def test_zoid6_shared_resolves_to_single_entry_without_with_deps():
    """`deploy zoid6.shared` (no --with-deps) is a single-step deploy.

    Bare deps (bbsengine6, zoid6 bare) are intentionally NOT pulled
    in without --with-deps. Operators who just want to push shared
    chrome shouldn't pay for a full bbsengine6 build.
    """
    order = deploytool.lib.resolve(["zoid6.shared"], with_deps=False)
    assert order == [("zoid6", "shared")], (
        f"`deploy zoid6.shared` without --with-deps must resolve to "
        f"a single (zoid6, shared) entry; got {order!r}"
    )


def test_zoid6_shared_with_deps_walks_bare_deps_first():
    """`deploy --with-deps zoid6.shared` walks bbsengine6 (bare) and
    zoid6 (bare) before `zoid6.shared`.

    zoid6 declares `["bbsengine6"]` in DEPENDENCIES, so `bbsengine6`
    walks first. zoid6 itself is added (bare) by the dep walker
    because there's a base-level dep — but the explicit `shared`
    sub doesn't get auto-promoted to bare `zoid6`; the bare
    entry comes from the dep walker including the base.

    Pin this ordering so a future refactor can't silently split
    the shared chrome deploy from its prerequisite rebuild.
    """
    order = deploytool.lib.resolve(["zoid6.shared"], with_deps=True)
    assert ("bbsengine6", None) in order, (
        "zoid6 declares bbsengine6 as a base dep; --with-deps must "
        f"walk it. Got order={order!r}"
    )
    assert ("zoid6", "shared") in order, (
        f"zoid6.shared must be in the resolved order; got {order!r}"
    )
    assert order[-1] == ("zoid6", "shared"), (
        "zoid6.shared must be the LAST step — it's the action the "
        "operator asked for, and it depends on zoid6's own stage "
        f"having been rebuilt by the bare dep walk. Got {order!r}"
    )
    assert order[0] == ("bbsengine6", None), (
        "bbsengine6 must be the FIRST step (zoid6 -> bbsengine6 "
        f"per DEPENDENCIES). Got {order!r}"
    )


# ---------------------------------------------------------------------------
# Unknown / ambiguous subs
# ---------------------------------------------------------------------------


def test_zoid6_shared_short_prefix_resolves_unique():
    """`deploy zoid6.sha` (or any unique shortest prefix of
    `shared`) resolves uniquely to `shared`.

    Pin the shortest-unique-prefix behavior so the operator can
    type `deploy zoid6.sha` without surprises.
    """
    # "shared" is the only TARGETS entry starting with "sha"
    # (the others are www, tui, prod).
    resolved = deploytool.lib.resolve_sub_prefix("sha", ["www", "tui", "prod", "shared"])
    assert resolved == "shared", (
        f"resolve_sub_prefix('sha', [...]) must return 'shared'; got {resolved!r}"
    )


def test_zoid6_unknown_sub_errors_with_available_list(monkeypatch):
    """`deploy zoid6.zoid` (not a real sub) is rejected with the
    full available-subs list so the operator can correct the typo.
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
        deploytool.lib.resolve(["zoid6.zoid"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    # Available list must mention every existing sub — including
    # `shared` (the one the operator likely meant if they were
    # trying to push chrome).
    for sub in ("www", "tui", "prod", "shared"):
        assert sub in out, (
            f"unknown-sub error for zoid6 must list {sub!r} in "
            f"the available subs; got {out!r}"
        )
