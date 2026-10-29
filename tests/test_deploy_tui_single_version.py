"""deploy-tui uses one version for the whole run, and install refuses to run without its wheel.

Regression: VERSION was a recursive ?= $(shell ...), so each reference re-ran next_version.sh. The
build and the wheel name then used different timestamps, and install failed on a missing wheel.
"""

import re
import shutil
import subprocess

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _make(*args):
    if shutil.which("make") is None:
        pytest.skip("make not available")
    return subprocess.run(["make", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=120)


@pytest.mark.unit
def test_version_is_evaluated_once():
    text = (ROOT / "Makefile").read_text()
    assert re.search(r"^VERSION\s*:=\s*\$\(VERSION\)", text, re.MULTILINE), "VERSION must be frozen with :="


@pytest.mark.unit
def test_deploy_tui_plan_uses_one_timestamp():
    r = _make("-n", "deploy-tui", "VERSION_SCRIPT=/bin/echo")
    stamps = set(re.findall(r"0\.0\.2\.dev\d+", r.stdout + r.stderr))
    assert len(stamps) <= 1, stamps


@pytest.mark.unit
def test_install_refuses_without_its_built_wheel():
    text = (ROOT / "Makefile").read_text()
    assert "run 'make build' first" in text
