"""Tests for the `wwworg` whole-target alias.

`SUB_ALIASES["wwworg"] = "bbsengine6.wwworg"` lets `deploy wwworg`
stand in for `deploy bbsengine6.wwworg`. The alias expands before the
`project.sub` split, so it resolves to the same chain and make target.
"""

import deploytool.lib


def test_wwworg_alias_resolves_to_bbsengine6_wwworg():
    order = deploytool.lib.resolve(["wwworg"], with_deps=False)
    assert order == [("bbsengine6", "wwworg")]


def test_wwworg_alias_matches_explicit_target():
    assert deploytool.lib.resolve(["wwworg"]) == deploytool.lib.resolve(
        ["bbsengine6.wwworg"]
    )


def test_wwworg_alias_composes_with_other_targets():
    order = deploytool.lib.resolve(["wwworg", "teos.www"], with_deps=False)
    assert order == [("bbsengine6", "wwworg"), ("teos", "www")]


def test_wwworg_alias_is_declared():
    assert deploytool.lib.SUB_ALIASES["wwworg"] == "bbsengine6.wwworg"
