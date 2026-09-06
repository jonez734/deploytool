"""Tests for bbsengine6's website sub-targets (wwworg + wwwcom)
and the handbook sub-target.

bbsengine6 exposes four subs under deploytool:

  - `bbsengine6.tui`      — Python wheel build + venv install
                           (via `deploy-tui`).
  - `bbsengine6.wwworg`   — stage + rsync the bbsengine.org website
                           (`bbsengine6/www/org`). Driven by the
                           `deploy-wwworg` wrapper in
                           `bbsengine6/Makefile`.
  - `bbsengine6.wwwcom`   — stage + rsync the bbsengine.com website
                           (`bbsengine6/www/com`). Driven by the
                           `deploy-wwwcom` wrapper.
  - `bbsengine6.handbook` — stage the handbook tree and ship the
                           blurb/markdown-rendered handler for
                           `https://bbsengine.org/handbook/<v>/<path>`.
                           Driven by the `deploy-handbook` wrapper.

These subs are the two website deploys (`bbsengine.org`,
`bbsengine.com`) that historically lived behind the legacy
`bbsengine6.www` sub (which actually deployed the engine library,
not the websites), plus the handbook. The legacy `www` sub is
removed: bare `deploy bbsengine6` now lists the four current subs
and exits 1, and a caller using the legacy `bbsengine6.www` gets
an "unknown sub-target" error naming the new ones.

These tests are the deploy-side counterpart to the bbsengine6
Makefile changes that introduced `deploy-wwworg` /
`deploy-wwwcom` / `deploy-handbook`. They guard against
regressions where someone removes one of the subs (silently
reverting to a smaller TARGETS) or breaks the make-rule wiring
on the bbsengine6 side.
"""

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# TARGETS shape
# ---------------------------------------------------------------------------


def test_bbsengine6_targets_has_four_subs():
    """bbsengine6 must expose exactly tui, wwworg, wwwcom, handbook.

    A single-sub TARGETS would let bare `deploy bbsengine6` auto-pick,
    defeating the operator's intent to be forced to name a sub.
    A two- or three-sub TARGETS would silently drop one of the four
    sub-targets (the handbook, or one of the website deploys).
    """
    targets = deploytool.lib.get_targets("bbsengine6")
    assert targets == ["tui", "wwworg", "wwwcom", "handbook"], (
        f"bbsengine6 TARGETS must be ['tui', 'wwworg', 'wwwcom', 'handbook']; "
        f"got {targets!r}. Bare `deploy bbsengine6` must stay ambiguous "
        "(warn + exit 1) so the operator names a sub explicitly, and both "
        "website deploys (bbsengine.org, bbsengine.com) plus the handbook "
        "must remain reachable."
    )


def test_bbsengine6_targets_does_not_contain_legacy_www():
    """Legacy `www` sub is gone; replaced by wwworg/wwwcom.

    `www` used to drive the engine library deploy via `php-deploy` +
    smarty rsync (see bbsengine6/Makefile `deploy-www: deploy`, removed
    alongside this change). Callers using the legacy `bbsengine6.www`
    should now see an "unknown sub-target" error listing the new subs.
    """
    targets = deploytool.lib.get_targets("bbsengine6")
    assert "www" not in targets, (
        f"legacy 'www' sub must be removed from bbsengine6 TARGETS; got {targets!r}"
    )


# ---------------------------------------------------------------------------
# Bare invocation: warn + exit
# ---------------------------------------------------------------------------


def test_bare_bbsengine6_is_ambiguous(monkeypatch):
    """`deploy bbsengine6` (bare) lists all four subs and exits 1."""
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
    assert "bbsengine6" in out, "resolver must name the ambiguous base"
    assert "tui" in out, "resolver must list tui in the available subs"
    assert "wwworg" in out, "resolver must list wwworg in the available subs"
    assert "wwwcom" in out, "resolver must list wwwcom in the available subs"
    assert "handbook" in out, "resolver must list handbook in the available subs"


def test_bare_bbsengine6_under_with_deps_is_also_ambiguous(monkeypatch):
    """`deploy --with-deps bbsengine6` (bare) is still ambiguous.

    `--with-deps` only controls dep walking, not sub expansion.
    Three-sub TARGETS still trips the ambiguity gate.
    """
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
        deploytool.lib.resolve(["bbsengine6"], with_deps=True)
    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# Explicit sub resolution
# ---------------------------------------------------------------------------


def test_explicit_tui_resolves_to_single_tui_entry():
    """`deploy bbsengine6.tui` -> [('bbsengine6', 'tui')]."""
    order = deploytool.lib.resolve(["bbsengine6.tui"], with_deps=False)
    assert order == [("bbsengine6", "tui")]


def test_explicit_wwworg_resolves_to_single_wwworg_entry():
    """`deploy bbsengine6.wwworg` -> [('bbsengine6', 'wwworg')]."""
    order = deploytool.lib.resolve(["bbsengine6.wwworg"], with_deps=False)
    assert order == [("bbsengine6", "wwworg")]


def test_explicit_wwwcom_resolves_to_single_wwwcom_entry():
    """`deploy bbsengine6.wwwcom` -> [('bbsengine6', 'wwwcom')]."""
    order = deploytool.lib.resolve(["bbsengine6.wwwcom"], with_deps=False)
    assert order == [("bbsengine6", "wwwcom")]


def test_explicit_handbook_resolves_to_single_handbook_entry():
    """`deploy bbsengine6.handbook` -> [('bbsengine6', 'handbook')].

    Mirror of test_explicit_wwworg_resolves_to_single_wwworg_entry for the
    handbook sub. The handbook sub has no `DEPENDENCIES` entry, so
    `with_deps=True` would still resolve to a single entry (no transitive
    walking). Verified separately below.
    """
    order = deploytool.lib.resolve(["bbsengine6.handbook"], with_deps=False)
    assert order == [("bbsengine6", "handbook")]


def test_handbook_under_with_deps_still_single_entry():
    """`deploy --with-deps bbsengine6.handbook` is a single-entry chain.

    `bbsengine6` has no `DEPENDENCIES` or `CONDITIONAL_DEPENDENCIES`
    entry, so `--with-deps` adds nothing. This guards against an
    accidental future addition of a dep that would silently pull in
    something the operator didn't ask for.
    """
    order = deploytool.lib.resolve(["bbsengine6.handbook"], with_deps=True)
    assert order == [("bbsengine6", "handbook")]


def test_both_www_subs_resolved_in_caller_order():
    """`deploy bbsengine6.wwworg bbsengine6.wwwcom` preserves caller order.

    No auto-expansion of the tui sub — only the named subs run.
    """
    order = deploytool.lib.resolve(
        ["bbsengine6.wwworg", "bbsengine6.wwwcom"], with_deps=False
    )
    assert order == [("bbsengine6", "wwworg"), ("bbsengine6", "wwwcom")]


def test_four_subs_resolved_in_caller_order():
    """`deploy bbsengine6.tui bbsengine6.wwworg bbsengine6.wwwcom
    bbsengine6.handbook` preserves caller order across all four."""
    order = deploytool.lib.resolve(
        [
            "bbsengine6.tui",
            "bbsengine6.wwworg",
            "bbsengine6.wwwcom",
            "bbsengine6.handbook",
        ],
        with_deps=False,
    )
    assert order == [
        ("bbsengine6", "tui"),
        ("bbsengine6", "wwworg"),
        ("bbsengine6", "wwwcom"),
        ("bbsengine6", "handbook"),
    ]


def test_legacy_www_sub_errors(monkeypatch):
    """`deploy bbsengine6.www` (the removed legacy sub) errors with the
    available list — confirms the rename took effect."""
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
        deploytool.lib.resolve(["bbsengine6.www"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "tui" in out
    assert "wwworg" in out
    assert "wwwcom" in out
    assert "handbook" in out


# ---------------------------------------------------------------------------
# Makefile target wiring (mirror what's expected on the bbsengine6 side)
# ---------------------------------------------------------------------------


def test_wwworg_make_target_is_deploy_wwworg():
    """run_make_deploy must construct 'deploy-wwworg' for bbsengine6.wwworg."""
    project = "bbsengine6"
    sub = "wwworg"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-wwworg"


def test_wwwcom_make_target_is_deploy_wwwcom():
    """run_make_deploy must construct 'deploy-wwwcom' for bbsengine6.wwwcom."""
    project = "bbsengine6"
    sub = "wwwcom"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-wwwcom"


def test_handbook_make_target_is_deploy_handbook():
    """run_make_deploy must construct 'deploy-handbook' for bbsengine6.handbook.

    Mirror of test_wwworg_make_target_is_deploy_wwworg for the handbook
    sub. No MAKE_TARGET_ALIASES override exists, so the target name
    follows the rule `deploy-{sub}` verbatim.
    """
    project = "bbsengine6"
    sub = "handbook"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-handbook"


def test_handbook_prod_does_not_chain_into_www_org():
    """`handbook-prod` must not invoke `www org`.

    Regression guard: `www org`'s recipe ends with an ssh rsync to
    host `merlin`, so chaining into it from a sub-target named
    `handbook` would incidentally ship the entire bbsengine.org site
    to production. Operators who want that push should run
    `deploy bbsengine6.wwworg`, which is the documented owner of
    the merlin rsync.
    """
    from pathlib import Path
    import re

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    m = re.search(r"^handbook-prod:.*?(?=^\S|\Z)", text, re.MULTILINE | re.DOTALL)
    body = m.group(0) if m else ""
    assert "www org" not in body, (
        "handbook-prod must not chain into '$(MAKE) -C www org' — "
        "that recipe ends with an ssh rsync to merlin. Use "
        "deploy bbsengine6.wwworg for the production push."
    )


def test_handbook_stage_submake_receives_version():
    """The handbook stage sub-make must receive VERSION from the parent.

    Regression guard for the empty-VERSION bug: the handbook stage
    sub-make must receive VERSION either via `export VERSION` or by
    passing `VERSION=$(VERSION)` inline, otherwise the rsync
    destination collapses to
    `/srv/www/vhosts/www.bbsengine.org/html/handbook//` (empty
    version segment) instead of a versioned directory.
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert "export VERSION" in text or "VERSION=$(VERSION)" in text, (
        "bbsengine6/Makefile must either `export VERSION` or pass "
        "`VERSION=$(VERSION)` to the handbook stage sub-make, otherwise "
        "the handbook rsync destination collapses to handbook/<empty>/."
    )


def test_bbsengine6_makefile_defines_deploy_handbook():
    """The bbsengine6 root Makefile must define a deploy-handbook target.

    Same "make target must exist" regression guard as the wwworg/wwwcom
    siblings: the deploytool-side TARGETS entry must line up with a real
    `deploy-handbook:` rule in the bbsengine6 Makefile, otherwise
    `deploy bbsengine6.handbook` silently fails at the make layer.
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "deploy-handbook:" in text, (
        f"bbsengine6/Makefile must define a deploy-handbook target. Got:\n{text}"
    )


def test_bbsengine6_makefile_defines_handbook_prod_target():
    """The deploy-handbook wrapper must delegate to a real handbook-prod target.

    Mirror of test_bbsengine6_makefile_defines_wwworg_target for handbook.
    `deploy-handbook: handbook-prod` is the conventional wire-up; without
    `handbook-prod:` the deploy is a no-op.
    """
    from pathlib import Path
    import re

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert re.search(r"^handbook-prod:", text, re.MULTILINE), (
        "bbsengine6/Makefile must define a `handbook-prod:` target that the "
        "deploy-handbook wrapper can delegate to."
    )


def test_bbsengine6_makefile_defines_deploy_wwworg():
    """The bbsengine6 root Makefile must define a deploy-wwworg target.

    Mirrors deploytool's "make target must exist" contract: if a
    TARGETS sub exists but no corresponding make rule, deploytool
    silently does the wrong thing (make fails with 'No rule to make
    target deploy-wwworg' but the deploy itself exits 0 because the
    subprocess was caught). Guarding here means a regression surfaces
    in CI, not in production.
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "deploy-wwworg:" in text, (
        f"bbsengine6/Makefile must define a deploy-wwworg target. Got:\n{text}"
    )


def test_bbsengine6_makefile_defines_deploy_wwwcom():
    """The bbsengine6 root Makefile must define a deploy-wwwcom target.

    Same regression guard as test_bbsengine6_makefile_defines_deploy_wwworg.
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "deploy-wwwcom:" in text, (
        f"bbsengine6/Makefile must define a deploy-wwwcom target. Got:\n{text}"
    )


def test_bbsengine6_makefile_defines_wwworg_target():
    """The deploy-wwworg wrapper must delegate to a real wwworg target.

    `deploy-wwworg: wwworg` is the conventional wire-up; without a
    `wwworg:` rule the deploy is a no-op. (The wwworg target itself
    delegates to `www/Makefile org`; this test only guards the
    bbsengine6/Makefile level.)
    """
    from pathlib import Path
    import re

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    # Match `^wwworg:` at the start of a line (not inside a comment).
    assert re.search(r"^wwworg:", text, re.MULTILINE), (
        "bbsengine6/Makefile must define a `wwworg:` target that the "
        "deploy-wwworg wrapper can delegate to."
    )


def test_bbsengine6_makefile_defines_wwwcom_target():
    """Same as test_bbsengine6_makefile_defines_wwworg_target but for wwwcom."""
    from pathlib import Path
    import re

    makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "Makefile"
    text = makefile.read_text()
    assert re.search(r"^wwwcom:", text, re.MULTILINE), (
        "bbsengine6/Makefile must define a `wwwcom:` target that the "
        "deploy-wwwcom wrapper can delegate to."
    )


# ---------------------------------------------------------------------------
# templates_c handling on the www push rsyncs
#
# templates_c is a Smarty *runtime* cache that lives on the remote
# (/srv/www/vhosts/{www.bbsengine.org,www.bbsengine.com}/templates_c/)
# and is referenced by config\SMARTYCOMPILEDTEMPLATESDIR in
# www/{org,com}/config-prod.php. It is NEVER a deploy artifact — the
# per-sub stage Makefiles may still mkdir it for local dev, but the
# push rsyncs in www/Makefile must --exclude it so:
#
#   1. an empty local templates_c/ doesn't rsync --delete the remote's
#      populated cache on every deploy;
#   2. freshly-created remote dirs end up group-writable + setgid
#      (`--chmod=Dg+rwxs`) so Smarty can write compiled templates
#      without operator intervention.
# ---------------------------------------------------------------------------


def test_www_push_rsyncs_exclude_templates_c_and_setgid_dirs():
    """Both push rsyncs in bbsengine6/www/Makefile must --exclude 'templates_c'
    and --chmod=Dg+rwxs.

    Regression guard for the bbsengine6.wwworg / bbsengine6.wwwcom deploy
    silently wiping the remote Smarty cache on every push (because stage
    creates templates_c/ empty locally and the rsync --delete-after walks
    into it). The push site is the single chokepoint where the protection
    belongs, so this test asserts the Makefile shape directly rather than
    chasing it through make-rule expansion.
    """
    from pathlib import Path

    www_makefile = Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "www" / "Makefile"
    assert www_makefile.is_file(), f"{www_makefile} not found"
    text = www_makefile.read_text()

    for needle in (
        '--exclude "templates_c"',
        "--chmod=Dg+rwxs",
    ):
        assert text.count(needle) == 2, (
            f"bbsengine6/www/Makefile: expected exactly two occurrences of "
            f"{needle!r} (one on the wwworg push, one on the wwwcom push); "
            f"got {text.count(needle)}. Both push rsyncs must protect the "
            f"remote templates_c/ cache the same way."
        )


def test_wwworg_and_wwwcom_stage_templates_c_locally_with_gitkeep():
    """Per-sub Makefiles keep their templates_c/ mkdir (for local dev)
    but add a .gitkeep so an empty stage dir doesn't confuse rsync.

    The push-rsync --exclude is what actually protects the remote; the
    local mkdir + .gitkeep exists so a developer running `make -C
    www/org stage` gets a usable templates_c/ on their workstation.
    """
    from pathlib import Path

    for sub, marker in (
        ("org", "ORGSTAGE"),
        ("com", "COMSTAGE"),
    ):
        makefile = (
            Path(deploytool.lib.SOURCE_BASE) / "bbsengine6" / "www" / sub / "Makefile"
        )
        text = makefile.read_text()
        assert f"mkdir -p $({marker})templates_c/" in text, (
            f"{sub}/Makefile: lost its templates_c/ mkdir. Local dev needs "
            f"the dir to exist for Smarty to compile templates into."
        )
        assert ".gitkeep" in text, (
            f"{sub}/Makefile: missing `touch .../templates_c/.gitkeep`. "
            f"Without the sentinel, rsync warns about an empty dir being "
            f"recreated on every push."
        )


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
