"""The wheelhouse: fill resolves the external tree for a target, check finds what is missing.

No network is used. ``fill`` is tested with pip stubbed, and the download command is checked as
text. The metadata for ``requirements_for`` is read from small wheels built in the test.
"""

import json
import zipfile

import pytest

from deploytool import wheelhouse


pytestmark = pytest.mark.unit


def _make_wheel(path, name, version, requires):
    """A minimal wheel whose METADATA lists ``requires`` as Requires-Dist lines."""
    dist = f"{name}-{version}.dist-info"
    meta = f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    meta += "".join(f"Requires-Dist: {r}\n" for r in requires)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist}/METADATA", meta)
        zf.writestr(f"{dist}/WHEEL", "Wheel-Version: 1.0\n")
    return str(path)


def test_internal_names_are_canonical():
    names = wheelhouse.internal_names(["BBSengine6-0.5.0-py3-none-any.whl", "bed-1-py3-none-any.whl"])
    assert names == {"bbsengine6", "bed"}


def test_requirements_drop_internal_packages_and_keep_external(tmp_path):
    bed = _make_wheel(tmp_path / "bed-0.5.0-py3-none-any.whl", "bed", "0.5.0",
                      ["bbsengine6>=0.5", "websockets>=12.0"])
    bbs = _make_wheel(tmp_path / "bbsengine6-0.5.0-py3-none-any.whl", "bbsengine6", "0.5.0",
                      ["bcrypt>=4.0", "psycopg[binary,pool]", "bed ; extra == 'x'"])
    reqs = wheelhouse.requirements_for([bed, bbs])
    assert "websockets>=12.0" in reqs
    assert "bcrypt>=4.0" in reqs
    assert "psycopg[binary,pool]" in reqs
    assert not any(r.startswith("bbsengine6") or r.startswith("bed") for r in reqs)


def test_download_command_targets_the_platform_not_the_host():
    cmd = wheelhouse.download_command(["pillow"], "/tmp/wh", platform="manylinux2014_x86_64",
                                      python_version="3.12", python="python")
    assert cmd[cmd.index("--platform") + 1] == "manylinux2014_x86_64"
    assert cmd[cmd.index("--python-version") + 1] == "3.12"
    assert "--only-binary=:all:" in cmd
    assert cmd[-1] == "pillow"


def test_fill_writes_an_index_of_what_it_fetched(tmp_path, monkeypatch):
    bed = _make_wheel(tmp_path / "bed-0.5.0-py3-none-any.whl", "bed", "0.5.0", ["websockets>=12"])
    wh = tmp_path / "wheelhouse"

    class Done:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kw):
        # pip would write the downloaded files; simulate that.
        (wh / "websockets-17.4-py3-none-any.whl").write_bytes(b"x")
        return Done()

    monkeypatch.setattr(wheelhouse.subprocess, "run", fake_run)
    index = wheelhouse.fill([bed], str(wh), platform="manylinux2014_x86_64")
    assert index["files"] == ["websockets-17.4-py3-none-any.whl"]
    assert json.loads((wh / wheelhouse.INDEX_NAME).read_text())["files"] == index["files"]


def test_fill_fails_loudly_when_pip_fails(tmp_path, monkeypatch):
    bed = _make_wheel(tmp_path / "bed-0.5.0-py3-none-any.whl", "bed", "0.5.0", ["nosuchpkg"])

    class Failed:
        returncode = 1
        stderr = "ERROR: No matching distribution found for nosuchpkg"

    monkeypatch.setattr(wheelhouse.subprocess, "run", lambda cmd, **kw: Failed())
    with pytest.raises(wheelhouse.WheelhouseError, match="No matching distribution"):
        wheelhouse.fill([bed], str(tmp_path / "wh"), platform="manylinux2014_x86_64")


def test_fill_with_no_external_requirements_writes_an_empty_index(tmp_path):
    bed = _make_wheel(tmp_path / "bed-0.5.0-py3-none-any.whl", "bed", "0.5.0", [])
    index = wheelhouse.fill([bed], str(tmp_path / "wh"), platform="manylinux2014_x86_64")
    assert index["requirements"] == [] and index["files"] == []


def test_check_reports_a_missing_distribution(tmp_path):
    wh = tmp_path / "wh"
    wh.mkdir()
    (wh / wheelhouse.INDEX_NAME).write_text(json.dumps({"files": ["a-1.whl", "b-1.whl"]}))
    (wh / "a-1.whl").write_bytes(b"x")
    assert wheelhouse.check(str(wh)) == ["b-1.whl"]


def test_check_is_clean_when_complete(tmp_path):
    wh = tmp_path / "wh"
    wh.mkdir()
    (wh / wheelhouse.INDEX_NAME).write_text(json.dumps({"files": ["a-1.whl"]}))
    (wh / "a-1.whl").write_bytes(b"x")
    assert wheelhouse.check(str(wh)) == []


def test_check_without_an_index_is_an_error(tmp_path):
    with pytest.raises(wheelhouse.WheelhouseError, match="fill the wheelhouse first"):
        wheelhouse.check(str(tmp_path))
