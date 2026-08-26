"""Tests for zoidoffice's two-sub deploy shape (tui + www).

zoidoffice uses deploytool's bare-base-multi-sub pattern:

  - TARGETS = ["tui", "www"]
  - `deploy zoidoffice` (bare) is ambiguous: resolve() lists the two
    subs and exits 1.
  - `deploy zoidoffice.tui` resolves to a single (zoidoffice, "tui")
    entry; the Makefile resolves it to `make -C zoidoffice deploy-tui`.
  - `deploy zoidoffice.www` resolves to (zoidoffice, "www"); Makefile
    runs `make deploy-www`, which builds + sdist + signs.

These tests are the deploy-side counterpart to the zoidoffice Makefile
changes that introduced deploy-www. They guard against regressions
where someone removes the second sub (reverting zoidoffice to a
single-sub base that would silently auto-pick on bare invocation).
"""

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# TARGETS shape
# ---------------------------------------------------------------------------


def test_zoidoffice_targets_has_two_subs():
    """zoidoffice must expose exactly tui and www.

    A single-sub TARGETS would let bare `deploy zoidoffice` auto-pick,
    defeating the operator's intent to be forced to name a sub.
    """
    targets = deploytool.lib.get_targets("zoidoffice")
    assert targets == ["tui", "www"], (
        f"zoidoffice TARGETS must be ['tui', 'www']; got {targets!r}. "
        "Bare `deploy zoidoffice` must stay ambiguous (warn + exit 1) "
        "so the operator names a sub explicitly."
    )


# ---------------------------------------------------------------------------
# Bare invocation: warn + exit
# ---------------------------------------------------------------------------


def test_bare_zoidoffice_is_ambiguous(monkeypatch):
    """`deploy zoidoffice` (bare) lists tui + www and exits 1."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["zoidoffice"], with_deps=False)
    assert excinfo.value.code == 1

    out = "\n".join(msgs)
    assert "zoidoffice" in out, "resolver must name the ambiguous base"
    assert "tui" in out, "resolver must list tui in the available subs"
    assert "www" in out, "resolver must list www in the available subs"


def test_bare_zoidoffice_under_with_deps_is_also_ambiguous(monkeypatch):
    """`deploy --with-deps zoidoffice` is still ambiguous; --with-deps
    only controls dep walking, not sub expansion."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["zoidoffice"], with_deps=True)
    assert excinfo.value.code == 1


# ---------------------------------------------------------------------------
# Explicit sub resolution
# ---------------------------------------------------------------------------


def test_explicit_tui_resolves_to_single_tui_entry():
    """`deploy zoidoffice.tui` -> [('zoidoffice', 'tui')]."""
    order = deploytool.lib.resolve(["zoidoffice.tui"], with_deps=False)
    assert order == [("zoidoffice", "tui")]


def test_explicit_www_resolves_to_single_www_entry():
    """`deploy zoidoffice.www` -> [('zoidoffice', 'www')]."""
    order = deploytool.lib.resolve(["zoidoffice.www"], with_deps=False)
    assert order == [("zoidoffice", "www")]


def test_both_subs_resolved_in_caller_order():
    """Caller-named subs keep their order; no auto-expansion."""
    order = deploytool.lib.resolve(
        ["zoidoffice.tui", "zoidoffice.www"], with_deps=False
    )
    assert order == [("zoidoffice", "tui"), ("zoidoffice", "www")]


def test_unknown_sub_target_errors(monkeypatch):
    """`deploy zoidoffice.prod` (not a real sub) is rejected with the
    available list."""
    msgs = []
    monkeypatch.setattr(
        deploytool.lib.io, "echo",
        lambda text, *a, **kw: msgs.append(text),
    )

    def fake_exit(rc=0):
        raise SystemExit(rc)

    monkeypatch.setattr(deploytool.lib.sys, "exit", fake_exit)
    with pytest.raises(SystemExit) as excinfo:
        deploytool.lib.resolve(["zoidoffice.prod"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "tui" in out and "www" in out


# ---------------------------------------------------------------------------
# Makefile target wiring (mirror what's expected on the zoidoffice side)
# ---------------------------------------------------------------------------


def test_zoidoffice_make_target_for_tui_is_deploy_tui():
    """run_make_deploy must construct 'deploy-tui' for zoidoffice.tui."""
    project = "zoidoffice"
    sub = "tui"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-tui"


def test_zoidoffice_make_target_for_www_is_deploy_www():
    """run_make_deploy must construct 'deploy-www' for zoidoffice.www."""
    project = "zoidoffice"
    sub = "www"
    sub = deploytool.lib.MAKE_TARGET_ALIASES.get((project, sub), sub)
    target = f"deploy-{sub}" if sub else "deploy"
    assert target == "deploy-www"


def test_zoidoffice_makefile_defines_deploy_www():
    """The zoidoffice root Makefile must define a deploy-www target.

    Mirrors deploytool's "make target must exist" contract: if a
    TARGETS sub exists but no corresponding make rule, deploytool
    silently does the wrong thing (make fails with 'No rule to make
    target deploy-www' but the deploy itself exits 0 because the
    subprocess was caught). Guarding here means a regression surfaces
    in CI, not in production.
    """
    from pathlib import Path

    makefile = Path(deploytool.lib.SOURCE_BASE) / "zoidoffice" / "Makefile"
    assert makefile.is_file(), f"{makefile} not found"
    text = makefile.read_text()
    assert "^deploy-www:" in text or "deploy-www:" in text, (
        "zoidoffice/Makefile must define a deploy-www target. "
        f"Got:\n{text}"
    )