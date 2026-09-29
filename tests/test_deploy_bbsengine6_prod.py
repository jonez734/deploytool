"""Tests for bbsengine6's `prod` sub-target — the engine-library umbrella.

bbsengine6 exposes a `prod` sub under deploytool (added 2026-09-29)
that runs the engine-library umbrella deploy in one command:

  - `bbsengine6.prod` — runs `make -C bbsengine6 deploy`, which is
                        the existing umbrella rule at
                        `bbsengine6/Makefile:286`. That rule does:
                          1. `make -C engine stage`     (bbsengine6/engine/*.php
                                                       -> /srv/www/bbsengine6/engine/)
                          2. `make -C engine deploy-engine`
                                                        (stage + merlin push
                                                         to zoidtechnologies.com/html/engine/)
                          3. `make -C skin stage`       (scss -> compiled tmpl
                                                       in /srv/www/bbsengine6/skin/)
                          4. `make php-deploy`          (bbsengine6/php/ ->
                                                       /srv/www/bbsengine6/php/)
                          5. mkdir + rsync smarty/      (bbsengine6/smarty/*.php ->
                                                       /srv/www/bbsengine6/smarty/)
                          6. RSYNC_MAX_DELETE precheck  (guard against
                                                       --delete-after wipes)
                          7. `rsync /srv/www/bbsengine6/ merlin:/srv/www/bbsengine6/`
                                                        (full umbrella push)

The user-facing sub name is `prod` while the make target stays the
existing `deploy:` rule — the alias lives at
`MAKE_TARGET_ALIASES[("bbsengine6", "prod")] = "deploy"`. This is
the same alias pattern used for `bed.tui -> venv` and
`zoid6.shared -> shared`.

`prod` replaces the legacy `www` sub (removed 2025) which mapped to
the same umbrella but was confused with the wwworg/wwwcom website
deploys. With `prod`, every chain that needs the bbsengine6 engine
library can name an explicit sub (`bbsengine6.prod`) instead of
relying on bare-base transitive behavior.

These tests are the deploy-side counterpart to the deploytool
changes that added `bbsengine6.prod` to TARGETS and the alias to
MAKE_TARGET_ALIASES. They guard against regressions where someone
removes the sub (silently reverting to a 7-sub TARGETS), breaks
the make-target alias, or breaks the explicit chain that consumes
it (zoid6.www, casino.www, article2.www, teos.www, teos.prod).
"""

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# TARGETS shape
# ---------------------------------------------------------------------------


def test_bbsengine6_targets_includes_prod():
    """bbsengine6 TARGETS must include the prod sub.

    The exact-list assertion lives in
    `test_deploy_bbsengine6_www.py::test_bbsengine6_targets_has_eight_subs`
    so the full shape is pinned there. This test focuses on the
    new `prod` entry: its presence, uniqueness, and slot position
    (between `wwwcom` and `handbook` so the two website deploys
    stay adjacent at the front of the list).
    """
    targets = deploytool.lib.get_targets("bbsengine6")
    assert "prod" in targets, (
        f"prod must be in bbsengine6 TARGETS; got {targets!r}"
    )
    assert targets.count("prod") == 1
    # Slot position: after `wwwcom`, before `handbook`. The two
    # website deploys (wwworg + wwwcom) lead the list, then the
    # engine-library umbrella (prod), then the handbook/engine
    # surface at the tail.
    assert targets.index("prod") == targets.index("wwwcom") + 1, (
        f"prod must immediately follow wwwcom in TARGETS; got {targets!r}"
    )
    assert targets.index("prod") < targets.index("handbook"), (
        f"prod must come before handbook in TARGETS; got {targets!r}"
    )


def test_bbsengine6_targets_does_not_contain_legacy_www():
    """Legacy `www` sub must NOT be re-added.

    The legacy `www` sub was removed in 2025 and replaced by
    wwworg/wwwcom for the website deploys. `bbsengine6.prod` is the
    successor to the engine-library umbrella that `www` used to
    trigger. A regression that re-adds `www` would create a
    ambiguous-prefix error (`www` matches `wwworg`, `wwwcom`, and
    `www`) and silently route callers to the wrong make target.
    """
    targets = deploytool.lib.get_targets("bbsengine6")
    assert "www" not in targets, (
        f"legacy 'www' sub must not return to bbsengine6 TARGETS; "
        f"got {targets!r}. Use wwworg / wwwcom / prod instead."
    )


# ---------------------------------------------------------------------------
# Explicit sub resolution
# ---------------------------------------------------------------------------


def test_explicit_prod_resolves_to_single_entry():
    """`deploy bbsengine6.prod` -> [('bbsengine6', 'prod')]."""
    order = deploytool.lib.resolve(["bbsengine6.prod"], with_deps=False)
    assert order == [("bbsengine6", "prod")]


def test_prod_under_with_deps_still_single_entry():
    """`deploy --with-deps bbsengine6.prod` is a single-entry chain.

    bbsengine6 has no transitive deps (DEPENDENCIES['bbsengine6'] is
    absent — the project is a leaf in the dep DAG), so --with-deps
    doesn't add anything. This pins that contract.
    """
    order = deploytool.lib.resolve(["bbsengine6.prod"], with_deps=True)
    assert order == [("bbsengine6", "prod")]


def test_prod_short_prefix_resolves_to_prod():
    """`deploy bbsengine6.p` (shortest unique prefix) resolves to `prod`.

    bbsengine6's TARGETS are `["tui", "wwworg", "wwwcom", "prod",
    "handbook", "handbook-prod", "engine-stage", "engine-prod"]` —
    only one entry starts with `p` (the new `prod` entry; `prod`
    is the only letter-p-prefixed sub; `handbook-prod` starts with
    `h`, `engine-prod` starts with `e`). So `bbsengine6.p` is a
    uniquely resolvable short prefix.
    """
    order = deploytool.lib.resolve(["bbsengine6.p"], with_deps=False)
    assert order == [("bbsengine6", "prod")]


def test_prod_not_shadowed_by_short_prefix_ambiguity():
    """The legacy `www` short prefix must NOT accidentally resolve to prod.

    Before the `prod` sub was added, `bbsengine6.www` was an
    ambiguous prefix error (matched `wwworg` + `wwwcom`). Now that
    `prod` is in TARGETS, `www` is still ambiguous (matches
    wwworg and wwwcom — both start with `www`) but `prod` doesn't
    start with `www` so it doesn't enter that ambiguity class.
    The shortest-prefix logic at `resolve_sub_prefix` should
    ignore `prod` when matching `www`.

    This test pins that contract so a future TARGETS reordering
    that moves `prod` to the front doesn't accidentally shadow the
    wwworg/wwwcom ambiguity.
    """
    targets = deploytool.lib.get_targets("bbsengine6")
    matches = [t for t in targets if t.startswith("www")]
    # The "www" prefix matches wwworg + wwwcom — both still in the
    # list. prod is NOT a match.
    assert "prod" not in matches
    assert set(matches) == {"wwworg", "wwwcom"}


# ---------------------------------------------------------------------------
# MAKE_TARGET_ALIASES
# ---------------------------------------------------------------------------


def test_prod_aliases_to_bare_deploy():
    """`deploy bbsengine6.prod` runs `make -C bbsengine6 deploy`,
    not `make deploy-prod`.

    The bbsengine6 root Makefile declares the umbrella target as
    a plain `deploy:` rule (not `deploy-prod:`). MAKE_TARGET_ALIASES
    routes the user-facing sub name `prod` to the actual make
    target `deploy`, following the same shape as `bed.tui -> venv`
    and `zoid6.shared -> shared`.
    """
    assert deploytool.lib.MAKE_TARGET_ALIASES.get(("bbsengine6", "prod")) == "deploy", (
        f"MAKE_TARGET_ALIASES[('bbsengine6', 'prod')] must be 'deploy'; "
        f"got {deploytool.lib.MAKE_TARGET_ALIASES.get(('bbsengine6', 'prod'))!r}. "
        f"The umbrella rule is a plain `deploy:` rule at "
        f"bbsengine6/Makefile:286 — not `deploy-prod:` — so the alias "
        f"is what bridges the user-facing sub name to the make target."
    )


# ---------------------------------------------------------------------------
# Makefile-level guard: bbsengine6/Makefile must define the umbrella rule
# ---------------------------------------------------------------------------


def test_bbsengine6_makefile_defines_deploy_umbrella():
    """bbsengine6/Makefile must define the `deploy:` umbrella rule.

    `bbsengine6.prod` aliases to `make -C bbsengine6 deploy` via
    MAKE_TARGET_ALIASES. If the `deploy:` rule disappears from
    bbsengine6/Makefile, the alias becomes a no-op (make errors
    with "No rule to make target 'deploy'"). This test guards
    against that regression by asserting the rule still exists
    in the Makefile text.
    """
    from pathlib import Path
    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    # The umbrella rule starts with `deploy:` (not `deploy-prod:`)
    # at the start of a line. We use a regex to avoid matching
    # unrelated `deploy-*` targets (deploy-wwworg, deploy-wwwcom,
    # deploy-engine-stage, deploy-engine-prod, deploy-handbook,
    # deploy-handbook-prod, deploy-tui).
    import re
    assert re.search(r"^deploy:", text, re.MULTILINE), (
        "bbsengine6/Makefile must define the bare `deploy:` umbrella "
        "rule (engine + skin + php + smarty stage+prod push). "
        "MAKE_TARGET_ALIASES[('bbsengine6', 'prod')] = 'deploy' "
        "delegates to this rule. Search for '^deploy:' (anchored to "
        "start of line) to avoid false matches on deploy-wwworg / "
        "deploy-wwwcom / deploy-engine-* / deploy-handbook* / deploy-tui."
    )


# ---------------------------------------------------------------------------
# Cross-project consumers: zoid6.www, casino.www, article2.www, teos.www,
# teos.prod all explicitly walk `bbsengine6.prod` in their --with-deps chain.
# ---------------------------------------------------------------------------


def test_zoid6_www_with_deps_walks_bbsengine6_prod():
    """`deploy --with-deps zoid6.www` includes bbsengine6.prod.

    Replaces the previous implicit reliance on bare-base bbsengine6
    (which silently emitted `('bbsengine6', None)` and ran
    `make -C bbsengine6 deploy`). The explicit edge makes the
    chain self-documenting.
    """
    order = deploytool.lib.resolve(["zoid6.www"], with_deps=True)
    assert ("bbsengine6", "prod") in order, (
        f"zoid6.www --with-deps must include ('bbsengine6', 'prod'); "
        f"got {order!r}. The CONDITIONAL_DEPENDENCIES['zoid6']['www'] "
        f"edge is what pulls it in."
    )
    assert order.index(("bbsengine6", "prod")) < order.index(("zoid6", "www")), (
        f"bbsengine6.prod must run before zoid6.www; got {order!r}"
    )


def test_casino_www_with_deps_walks_bbsengine6_prod():
    """`deploy --with-deps casino.www` includes bbsengine6.prod.

    The previous CONDITIONAL_DEPENDENCIES edge was
    `("bbsengine6", "www")` — invalid because the legacy `www` sub
    was removed in 2025. The resolver emitted the edge anyway
    (visit() doesn't validate transitive edges) and at deploy
    time `make -C bbsengine6 deploy-www` errored with "No rule to
    make target deploy-www". The chain was effectively broken;
    the new `("bbsengine6", "prod")` edge fixes it.
    """
    order = deploytool.lib.resolve(["casino.www"], with_deps=True)
    assert ("bbsengine6", "prod") in order, (
        f"casino.www --with-deps must include ('bbsengine6', 'prod'); "
        f"got {order!r}. The CONDITIONAL_DEPENDENCIES['casino']['www'] "
        f"edge is what pulls it in. The previous ('bbsengine6', 'www') "
        f"edge was broken because the legacy www sub was removed."
    )
    assert order.index(("bbsengine6", "prod")) < order.index(("casino", "www")), (
        f"bbsengine6.prod must run before casino.www; got {order!r}"
    )


def test_article2_www_with_deps_walks_bbsengine6_prod():
    """`deploy --with-deps article2.www` includes bbsengine6.prod.

    Same fix as casino.www above — the previous `("bbsengine6", "www")`
    edge was invalid.
    """
    order = deploytool.lib.resolve(["article2.www"], with_deps=True)
    assert ("bbsengine6", "prod") in order, (
        f"article2.www --with-deps must include ('bbsengine6', 'prod'); "
        f"got {order!r}. The CONDITIONAL_DEPENDENCIES['article2']['www'] "
        f"edge is what pulls it in."
    )
    assert order.index(("bbsengine6", "prod")) < order.index(("article2", "www")), (
        f"bbsengine6.prod must run before article2.www; got {order!r}"
    )


def test_teos_www_with_deps_walks_bbsengine6_prod():
    """`deploy --with-deps teos.www` includes bbsengine6.prod.

    Mirrors the per-consumer assertions above for the teos.www
    chain. The previous chain silently walked bare-base bbsengine6
    (via DEPENDENCIES['teos']=['bbsengine6', 'zoid6']); the new
    explicit edge in CONDITIONAL_DEPENDENCIES['teos']['www'] makes
    it intentional. (Pinned separately in test_deploy_with_deps.py.)
    """
    order = deploytool.lib.resolve(["teos.www"], with_deps=True)
    assert ("bbsengine6", "prod") in order
    assert order.index(("bbsengine6", "prod")) < order.index(("teos", "www")), (
        f"bbsengine6.prod must run before teos.www; got {order!r}"
    )


def test_teos_prod_with_deps_walks_bbsengine6_prod():
    """`deploy --with-deps teos.prod` includes bbsengine6.prod.

    The teos.prod sub is the single-command surface for "stage and
    install everything required for teos". The chain is
    bbsengine6.prod -> zoid6.shared -> teos.engine -> teos.prod.
    (Full chain shape pinned in test_deploy_with_deps.py.)
    """
    order = deploytool.lib.resolve(["teos.prod"], with_deps=True)
    assert ("bbsengine6", "prod") in order
    assert order.index(("bbsengine6", "prod")) < order.index(("teos", "prod")), (
        f"bbsengine6.prod must run before teos.prod; got {order!r}"
    )


# ---------------------------------------------------------------------------
# Bare-base dedup: DEPENDENCIES edges that point at bare bbsengine6 must
# not double-fire when an explicit bbsengine6.prod edge also walks the same
# project. (lib.resolve dedups at lines 465-474: `if sub is None and name
# in has_sub: continue`.)
# ---------------------------------------------------------------------------


def test_teos_www_does_not_double_walk_bbsengine6():
    """`deploy --with-deps teos.www` walks bbsengine6 exactly once.

    DEPENDENCIES['teos'] = ['bbsengine6', 'zoid6'] walks bare-base
    bbsengine6 (which would emit `('bbsengine6', None)` in the
    order). The new CONDITIONAL_DEPENDENCIES['teos']['www'] entry
    also walks `('bbsengine6', 'prod')`. lib.resolve must dedup so
    only the explicit prod entry survives; the bare-base entry is
    dropped at line 469 (`if sub is None and name in has_sub: continue`).
    """
    order = deploytool.lib.resolve(["teos.www"], with_deps=True)
    bbsengine6_entries = [x for x in order if x[0] == "bbsengine6"]
    assert bbsengine6_entries == [("bbsengine6", "prod")], (
        f"bbsengine6 must appear exactly once in the teos.www "
        f"--with-deps chain, as ('bbsengine6', 'prod'); got "
        f"{bbsengine6_entries!r}. lib.resolve must dedup the bare-base "
        f"entry from DEPENDENCIES['teos'] against the explicit "
        f"('bbsengine6', 'prod') entry from CONDITIONAL_DEPENDENCIES."
    )


def test_zoid6_www_does_not_double_walk_bbsengine6():
    """`deploy --with-deps zoid6.www` walks bbsengine6 exactly once.

    DEPENDENCIES['zoid6'] = ['bbsengine6'] walks bare-base bbsengine6
    (which would emit `('bbsengine6', None)` in the order). The
    new CONDITIONAL_DEPENDENCIES['zoid6']['www'] entry also walks
    `('bbsengine6', 'prod')`. Same dedup as test_teos_www_does_not_double_walk_bbsengine6.
    """
    order = deploytool.lib.resolve(["zoid6.www"], with_deps=True)
    bbsengine6_entries = [x for x in order if x[0] == "bbsengine6"]
    assert bbsengine6_entries == [("bbsengine6", "prod")], (
        f"bbsengine6 must appear exactly once in the zoid6.www "
        f"--with-deps chain, as ('bbsengine6', 'prod'); got "
        f"{bbsengine6_entries!r}."
    )


# ---------------------------------------------------------------------------
# Legacy www sub is now an "unknown sub-target" error
# ---------------------------------------------------------------------------


def test_legacy_bbsengine6_www_errors(monkeypatch):
    """`deploy bbsengine6.www` must error with the unknown-sub-target
    message, naming the eight current subs.

    The legacy `www` sub was removed in 2025 (replaced by
    wwworg/wwwcom for the websites and now `prod` for the
    engine-library umbrella). A regression that re-adds it would
    shadow nothing (it's distinct from `wwworg` and `wwwcom` at
    the full-name level), but it would still re-introduce the
    confusion that motivated its removal in the first place.
    Pin that callers get the explicit error.
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
        deploytool.lib.resolve(["bbsengine6.www"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "unknown sub-target" in out or "ambiguous" in out, (
        f"legacy bbsengine6.www must error; got {out!r}"
    )
    # Either message lists the available subs; both must include `prod`.
    assert "prod" in out, (
        f"error message must list `prod` as an available sub; got {out!r}"
    )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
