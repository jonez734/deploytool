"""Tests for shortest-unique-prefix sub-target matching in `lib.resolve`.

The sub string on the command line is normally a full sub name
(`bbsengine6.handbook`, `zoid6.prod`, `casino.tui`). The resolver
also accepts the **shortest unique prefix** of a sub name within
that project's `TARGETS` list:

  - `bbsengine6.h`      -> handbook   (only one match)
  - `bbsengine6.hand`   -> handbook
  - `bbsengine6.wwwco`  -> wwwcom     (wwworg excluded by length)
  - `zoid6.p`           -> prod
  - `casino.t`          -> tui
  - `bbsengine6.www`    -> ERROR      (matches both wwworg and wwwcom;
                                       prefix is ambiguous)
  - `bbsengine6.x`      -> ERROR      (no match; existing
                                       "unknown sub-target" message)
  - `bbsengine6.handbook` -> handbook (exact match still wins)

This is **not** a fuzzy match — typos like `hanbook` still error.
Prefix matching is **per-base** (only within that project's
`TARGETS`), so `zoid6.p` resolving to `prod` does not affect other
projects.

Implementation: `lib.resolve_sub_prefix(sub, targets)`
(`src/deploytool/lib.py:149`) is the helper. The contract is:

  - exact match -> returns the canonical sub name (str)
  - unique prefix -> returns the canonical sub name (str)
  - ambiguous prefix -> returns `(None, [matches...])`; the resolver
    emits a distinct "ambiguous sub-target prefix" error and exits 1.
  - no match -> returns `None`; the resolver emits the existing
    "unknown sub-target" error and exits 1.

Regression guard for the original exact-match contract is implicit
in every other test file (test_deploy_bbsengine6_www.py,
test_deploy_with_deps.py, etc.) which uses fully-spelled subs and
must continue to pass.
"""

import pytest

import deploytool.lib


# ---------------------------------------------------------------------------
# resolve_sub_prefix unit tests (pure function)
# ---------------------------------------------------------------------------


def test_exact_match_returns_sub_unchanged():
    """Exact match wins verbatim — preserves every existing test."""
    assert deploytool.lib.resolve_sub_prefix("handbook", ["tui", "wwworg", "wwwcom", "handbook"]) == "handbook"


def test_exact_match_wins_over_prefix_match():
    """When `sub` is in targets, the prefix scan never runs.

    E.g. `wwworg` matches both `wwworg` (exact) and a hypothetical
    `www` (prefix). Exact must win — otherwise a typo `www` would
    shadow `wwworg` and the contract would silently shift.
    """
    targets = ["tui", "wwworg", "wwwcom", "handbook"]
    assert deploytool.lib.resolve_sub_prefix("wwworg", targets) == "wwworg"


def test_unique_prefix_returns_match():
    """Single prefix match returns the canonical sub name."""
    assert deploytool.lib.resolve_sub_prefix("hand", ["tui", "wwworg", "wwwcom", "handbook"]) == "handbook"


def test_one_char_unique_prefix_returns_match():
    """The user's literal example: `h` -> handbook in bbsengine6."""
    assert deploytool.lib.resolve_sub_prefix("h", ["tui", "wwworg", "wwwcom", "handbook"]) == "handbook"


def test_ambiguous_prefix_returns_tuple_with_matches():
    """Multiple prefix matches return `(None, [matches])`.

    Caller distinguishes this from `None` (no match) so the error
    message can name the candidates.
    """
    result = deploytool.lib.resolve_sub_prefix("www", ["tui", "wwworg", "wwwcom", "handbook"])
    assert result == (None, ["wwworg", "wwwcom"])


def test_no_match_returns_none():
    """No prefix match returns `None` — caller emits 'unknown sub-target'."""
    assert deploytool.lib.resolve_sub_prefix("x", ["tui", "wwworg", "wwwcom", "handbook"]) is None


def test_match_is_case_sensitive():
    """Match is case-sensitive — current code is strictly lowercase."""
    targets = ["tui", "wwworg", "wwwcom", "handbook"]
    assert deploytool.lib.resolve_sub_prefix("HAND", targets) is None
    assert deploytool.lib.resolve_sub_prefix("Hand", targets) is None


def test_match_is_prefix_anchored_not_substring():
    """`www` matches `wwworg`/`wwwcom` by prefix; `org` does NOT match.

    The helper uses `str.startswith`, not `in`. Substring matching
    would produce surprises (e.g. `org` matching `wwworg` while
    leaving `wwwcom` ambiguous — the user asked for prefix).
    """
    targets = ["tui", "wwworg", "wwwcom", "handbook"]
    assert deploytool.lib.resolve_sub_prefix("org", targets) is None


def test_prod_prefix_resolves_in_zoid6():
    """`zoid6.p` -> `prod` (only one entry starts with `p`)."""
    assert deploytool.lib.resolve_sub_prefix("p", ["www", "tui", "prod"]) == "prod"


def test_ambiguous_t_prefix_in_some_target_lists():
    """A prefix that matches >1 entry returns the ambiguous tuple.

    Demonstrates the helper is independent of the project's domain —
    any prefix string with multiple matches triggers the error path.
    """
    result = deploytool.lib.resolve_sub_prefix("w", ["www", "tui", "wombat"])
    assert result == (None, ["www", "wombat"])


def test_empty_string_is_not_a_prefix():
    """Empty `sub` string would match every target — treated as
    ambiguous (caller's bare-base branch already handles no-sub).

    `resolve_sub_prefix("", ...)` is unreachable through the normal
    command-line path because the parser splits on `.` and bare-base
    is dispatched separately. But if someone calls the helper
    directly with `""`, every entry starts-with `""`, so we get the
    ambiguous tuple — defensive against accidental reuse.
    """
    result = deploytool.lib.resolve_sub_prefix("", ["tui", "www"])
    assert result == (None, ["tui", "www"])


# ---------------------------------------------------------------------------
# resolve() integration tests (end-to-end through the resolver)
# ---------------------------------------------------------------------------


def test_resolve_bbsengine6_hand_prefix():
    """`deploy bbsengine6.hand` -> [('bbsengine6', 'handbook')]."""
    order = deploytool.lib.resolve(["bbsengine6.hand"], with_deps=False)
    assert order == [("bbsengine6", "handbook")]


def test_resolve_bbsengine6_h_prefix():
    """The literal example from the change request: `h` -> handbook."""
    order = deploytool.lib.resolve(["bbsengine6.h"], with_deps=False)
    assert order == [("bbsengine6", "handbook")]


def test_resolve_bbsengine6_wwwco_prefix_distinguishes_wwworg_from_wwwcom():
    """`wwwco` -> wwwcom; the prefix scan picks the unique match."""
    order = deploytool.lib.resolve(["bbsengine6.wwwco"], with_deps=False)
    assert order == [("bbsengine6", "wwwcom")]


def test_resolve_bbsengine6_wwwor_prefix_distinguishes_wwworg_from_wwwcom():
    """`wwwor` -> wwworg; mirror of the wwwco test."""
    order = deploytool.lib.resolve(["bbsengine6.wwwor"], with_deps=False)
    assert order == [("bbsengine6", "wwworg")]


def test_resolve_zoid6_p_prefix_to_prod():
    """`deploy zoid6.p` -> [('zoid6', 'prod')]."""
    order = deploytool.lib.resolve(["zoid6.p"], with_deps=False)
    assert order == [("zoid6", "prod")]


def test_resolve_bed_p_prefix_to_prod():
    """`bed.p` -> prod (only one entry starts with `p`)."""
    order = deploytool.lib.resolve(["bed.p"], with_deps=False)
    assert order == [("bed", "prod")]


def test_resolve_mistermcfeely_p_prefix_to_prod():
    """`mistermcfeely.p` -> prod (mirrors zoid6/bed)."""
    order = deploytool.lib.resolve(["mistermcfeely.p"], with_deps=False)
    assert order == [("mistermcfeely", "prod")]


def test_resolve_prefix_marks_sub_as_explicit():
    """A prefix-resolved sub is `explicit` for the prod-drop guard.

    `lib.py:378` strips auto-expanded `prod` subs from the final
    order. `zoid6.p` is user-named (not auto-expanded), so it must
    remain in the chain. Verified via the explicit-sub pathway:
    `resolve_sub_prefix` returns a sub name that gets added to
    `explicit_subs`, which keeps it past the drop guard.
    """
    order = deploytool.lib.resolve(["zoid6.p"], with_deps=False)
    assert order == [("zoid6", "prod")], (
        "zoid6.p resolves to prod and must stay in the chain — "
        "the user named it explicitly via prefix, so lib.py:378's "
        "`prod` drop guard must not apply."
    )


# ---------------------------------------------------------------------------
# Ambiguous-prefix error path
# ---------------------------------------------------------------------------


def test_resolve_ambiguous_prefix_errors_with_new_message(monkeypatch):
    """`bbsengine6.www` (matches both wwworg and wwwcom) errors with
    the *ambiguous* message — NOT the unknown-sub message.

    The two error classes are intentionally distinct: "unknown"
    means the prefix matched nothing; "ambiguous" means it matched
    more than one. Conflating them would hide real bugs (a typo
    looks like an ambiguous prefix).
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
        deploytool.lib.resolve(["bbsengine6.www"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "ambiguous" in out, (
        "ambiguous-prefix errors must use a distinct message naming the "
        f"candidates. Got: {out!r}"
    )
    assert "wwworg" in out
    assert "wwwcom" in out


def test_resolve_unknown_sub_still_uses_unknown_message(monkeypatch):
    """`bbsengine6.x` (no match) still uses the original
    'unknown sub-target' message — the new feature did not change
    the existing error class.
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
        deploytool.lib.resolve(["bbsengine6.x"], with_deps=False)
    assert excinfo.value.code == 1
    out = "\n".join(msgs)
    assert "unknown sub-target" in out, (
        "no-match errors must keep the legacy message verbatim. "
        f"Got: {out!r}"
    )
    assert "ambiguous" not in out


# ---------------------------------------------------------------------------
# Per-base scoping (a sub prefix does not leak across projects)
# ---------------------------------------------------------------------------


def test_resolve_per_base_scoping_isolates_prod_prefix():
    """`zoid6.p` resolves to `prod`; `mistermcfeely.p` resolves to
    `prod`; both are independent. A regression that lifted the
    prefix scan to a project-global lookup would still pass these
    two — but a regression that conflated TARGETS across bases
    would fail this combined assertion.
    """
    z = deploytool.lib.resolve(["zoid6.p"], with_deps=False)
    m = deploytool.lib.resolve(["mistermcfeely.p"], with_deps=False)
    assert z == [("zoid6", "prod")]
    assert m == [("mistermcfeely", "prod")]


def test_resolve_prefix_does_not_match_a_base_only_sub():
    """A prefix that resolves in one project's TARGETS does not
    silently apply to a project with no TARGETS entry.

    `letteredolive` is in DEPENDENCIES but has no TARGETS — it's a
    bare-base project that runs `make deploy` directly. The
    sub-resolution branch at `lib.py:350-351` only fires when
    `TARGETS[base]` is truthy, so for a base with no TARGETS the
    sub string is dropped entirely (the bare `make deploy` target
    runs). Per-base scoping is preserved: a `.t` on `letteredolive`
    does NOT invoke the prefix resolver (which would match `tui`
    in other projects' TARGETS).
    """
    import deploytool.lib as lib

    original_echo = lib.io.echo
    captured = []
    lib.io.echo = lambda text, *a, **kw: captured.append(text)
    try:
        order = lib.resolve(["letteredolive.t"], with_deps=False)
    finally:
        lib.io.echo = original_echo
    assert order == [("letteredolive", None)], (
        "letteredolive has no TARGETS; the sub string is dropped and "
        "the bare deploy runs. Per-base scoping means a sub prefix "
        "resolves only inside the project's own TARGETS list."
    )


# ---------------------------------------------------------------------------
# Multiple prefix-resolved subs in one command line
# ---------------------------------------------------------------------------


def test_resolve_multiple_prefix_subs_in_one_command():
    """Caller can mix prefix-resolved subs with full-name subs.

    `deploy bbsengine6.h bbsengine6.wwwco` -> handbook, wwwcom.
    """
    order = deploytool.lib.resolve(
        ["bbsengine6.h", "bbsengine6.wwwco"],
        with_deps=False,
    )
    assert order == [("bbsengine6", "handbook"), ("bbsengine6", "wwwcom")]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
