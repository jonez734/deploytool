"""Pins the deploytool sub-target shape: tui, prod, pypi, testpypi.

Regression guards for:

1. Upload and publish subs are opt-in. A dependency walk must never
   pull `prod`, `pypi`, or `testpypi` in, and a bare name must not
   auto-pick an upload.
2. Only `repo` writes to /srv/repo, and `REPO_DEST` defaults there.
3. `pypi` and `testpypi` refuse without PYPI_CONFIRM=1 and without
   TWINE_* credentials, and upload only this version's artifacts.
4. `SOURCE_BASE` is overridable via DEPLOYTOOL_SOURCE_BASE.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

import deploytool.lib


REPO_ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = REPO_ROOT / "Makefile"


def _makefile() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def test_deploytool_targets_are_tui_prod_pypi_testpypi():
    assert deploytool.lib.TARGETS["deploytool"] == [
        "tui",
        "prod",
        "pypi",
        "testpypi",
    ]


def test_upload_and_prod_subs_are_opt_in():
    assert {"prod", "pypi", "testpypi"} <= deploytool.lib.OPT_IN_SUBS
    assert deploytool.lib.UPLOAD_SUBS == {"pypi", "testpypi"}


@pytest.mark.parametrize("sub", ["prod", "pypi", "testpypi"])
def test_explicit_opt_in_sub_resolves(sub):
    order = deploytool.lib.resolve([f"deploytool.{sub}"], with_deps=False)
    assert order == [("deploytool", sub)]


def test_bare_deploytool_is_ambiguous_because_prod_counts():
    """`prod` counts toward ambiguity (as for mistermcfeely), so a bare
    `deploy deploytool` exits and lists the subs rather than guessing."""
    with pytest.raises(SystemExit):
        deploytool.lib.resolve(["deploytool"], with_deps=False)


def test_bare_name_ignores_upload_subs_when_picking_default():
    """Upload subs never count toward a bare-name auto-pick."""
    # getdate_next has tui + pypi + testpypi; only tui counts.
    assert deploytool.lib.resolve(["getdate_next"], with_deps=False) == [
        ("getdate_next", "tui")
    ]


def test_upload_subs_never_pulled_in_by_dependency_walk():
    """A project that depends on deploytool must not drag its uploads in."""
    order = deploytool.lib.resolve(["deploytool.tui"], with_deps=True)
    assert all(sub not in deploytool.lib.OPT_IN_SUBS for _, sub in order)


def test_repo_default_is_srv_repo_deploytool():
    text = _makefile()
    assert re.search(r"^REPO_DEST \?= /srv/repo/deploytool/$", text, re.M)


def test_only_repo_target_touches_srv_repo():
    """Every recipe line that references /srv/repo lives under `repo`.

    We can't parse Make fully, so check that the only rsync to REPO_DEST
    is in the `repo:` rule, and that no other rule names /srv/repo.
    """
    lines = _makefile().splitlines()
    current = None
    offenders = []
    for line in lines:
        m = re.match(r"^([A-Za-z0-9_.-]+):", line)
        if m:
            current = m.group(1)
        if "/srv/repo" in line and not line.lstrip().startswith("#"):
            # The default lives on a variable assignment, not in a rule.
            if current is None and line.startswith("REPO_DEST"):
                continue
            if current != "repo":
                offenders.append((current, line))
    assert offenders == [], f"/srv/repo referenced outside `repo`: {offenders}"


def test_prod_runs_tui_then_repo():
    text = _makefile()
    assert re.search(r"^prod: deploy-tui repo$", text, re.M)


def test_upload_targets_require_confirm_and_credentials():
    text = _makefile()
    for target in ("testpypi", "pypi"):
        assert re.search(
            rf"^{target}:.*\n\t@test \"\$\(PYPI_CONFIRM\)\" = \"1\"", text, re.M
        ), f"{target} must require PYPI_CONFIRM=1 before uploading"
    assert "TWINE_USERNAME must be __token__" in text
    assert "TWINE_PASSWORD is not set" in text


def test_upload_targets_upload_only_this_version_artifacts():
    text = _makefile()
    assert "ARTIFACTS = $(OUTDIR)$(PROJECT)-$(VERSION)*" in text
    assert "twine upload $(ARTIFACTS)*" in text
    assert "--repository-url $(TESTPYPI_URL) $(ARTIFACTS)*" in text


def test_version_is_pinned_so_stage_and_publish_match():
    assert re.search(r"^VERSION \?= ", _makefile(), re.M)


def test_pypi_refuses_without_confirm(tmp_path):
    """`make pypi` with no PYPI_CONFIRM must stop before any upload."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("TWINE_")}
    env.pop("PYPI_CONFIRM", None)
    # Dry-run: -n prints the recipe without running it. We assert on the
    # actual refusal by running the guard directly with an empty confirm.
    result = subprocess.run(
        ["make", "-s", "-C", str(REPO_ROOT), "-o", "check", "pypi"],
        capture_output=True,
        text=True,
        env=env,
    )
    # `check` is stubbed out via -o so no build runs; the confirm guard fires.
    assert result.returncode != 0
    assert "set PYPI_CONFIRM=1" in (result.stderr + result.stdout)


def test_source_base_respects_env_override(monkeypatch, tmp_path):
    """DEPLOYTOOL_SOURCE_BASE overrides the default checkout root."""
    import importlib

    monkeypatch.setenv("DEPLOYTOOL_SOURCE_BASE", str(tmp_path))
    reloaded = importlib.reload(deploytool.lib)
    try:
        assert reloaded.SOURCE_BASE == str(tmp_path)
    finally:
        monkeypatch.delenv("DEPLOYTOOL_SOURCE_BASE", raising=False)
        importlib.reload(deploytool.lib)
