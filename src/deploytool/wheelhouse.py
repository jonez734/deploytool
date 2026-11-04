"""Fill and check a bed instance's wheelhouse: the external dependencies for an offline install.

``fill`` runs where the package index is reachable. It resolves the full dependency tree of the
instance's internal wheels for the target platform, downloads every needed wheel into the wheelhouse
directory, and writes an index of what it fetched. The wheelhouse is then copied to the deployment.

``check`` runs on the target, or before a copy. It confirms that the wheelhouse holds every
distribution the index lists, so a missing file is found before an install fails on it.

Internal packages are not downloaded here: they come from the instance's dist directory.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

from packaging.utils import canonicalize_name, parse_wheel_filename

#: The index file written into the wheelhouse, listing every fetched distribution.
INDEX_NAME = "wheelhouse-index.json"

#: The default target platform: the 64-bit Linux hosts this deployment runs on. Override with
#: --platform when the target differs. Wheels are selected for this, not for the download machine.
DEFAULT_PLATFORM = "manylinux2014_x86_64"


class WheelhouseError(RuntimeError):
    """Raised when the wheelhouse cannot be filled or does not match its index."""


def internal_names(wheel_names: Iterable[str]) -> set[str]:
    """Canonical (PEP 503) distribution names of the internal wheels, so they are never downloaded."""
    names = set()
    for w in wheel_names:
        name, _version, _build, _tags = parse_wheel_filename(w)
        names.add(canonicalize_name(str(name)))
    return names


def download_command(
    requirements: Sequence[str],
    dest: str,
    *,
    platform: str,
    python_version: str,
    python: str = sys.executable,
) -> list[str]:
    """The pip command that downloads ``requirements`` and their dependencies for a target platform.

    ``--only-binary=:all:`` makes every file a wheel, so nothing is built on the download machine.
    ``--platform`` and ``--python-version`` select the target's wheels, not the download machine's.
    """
    cmd = [
        python, "-m", "pip", "download",
        "--dest", dest,
        "--only-binary=:all:",
        "--platform", platform,
        "--python-version", python_version,
        "--implementation", "cp",
    ]
    cmd += list(requirements)
    return cmd


def requirements_for(internal_wheel_paths: Iterable[str]) -> list[str]:
    """The external requirements of the internal wheels, from their ``Requires-Dist`` metadata.

    Internal packages are dropped from the list, since they come from the dist directory. Extras and
    markers are kept as written, so the download resolves the same tree the install will need.
    """
    import zipfile

    from packaging.requirements import Requirement

    internal = internal_names(os.path.basename(p) for p in internal_wheel_paths)
    reqs: dict[str, str] = {}
    for path in internal_wheel_paths:
        with zipfile.ZipFile(path) as zf:
            meta_name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
            metadata = zf.read(meta_name).decode("utf-8", "replace")
        for line in metadata.splitlines():
            if not line.startswith("Requires-Dist:"):
                continue
            spec = line.split(":", 1)[1].strip()
            req = Requirement(spec)
            if canonicalize_name(req.name) in internal:
                continue
            reqs.setdefault(spec, spec)
    return sorted(reqs)


def fill(
    internal_wheel_paths: Sequence[str],
    wheelhouse: str,
    *,
    platform: str,
    python_version: str = "3.12",
    timeout: Optional[int] = 900,
) -> dict:
    """Download the external tree of the internal wheels into ``wheelhouse`` and write its index.

    Returns the index dict. Raises :class:`WheelhouseError` if pip fails, so a partial download is
    never reported as complete.
    """
    os.makedirs(wheelhouse, exist_ok=True)
    reqs = requirements_for(internal_wheel_paths)
    if not reqs:
        index = {"platform": platform, "python": python_version, "requirements": [], "files": []}
    else:
        cmd = download_command(reqs, wheelhouse, platform=platform, python_version=python_version)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode != 0:
            raise WheelhouseError(f"pip download failed (rc={result.returncode}): {result.stderr.strip()[-800:]}")
        files = sorted(p.name for p in Path(wheelhouse).iterdir() if p.suffix == ".whl")
        index = {"platform": platform, "python": python_version, "requirements": reqs, "files": files}
    Path(wheelhouse, INDEX_NAME).write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return index


def check(wheelhouse: str) -> list[str]:
    """Return the distributions the index lists that are missing from ``wheelhouse``.

    An empty list means the wheelhouse is complete. A missing index is a :class:`WheelhouseError`.
    """
    index_path = Path(wheelhouse, INDEX_NAME)
    if not index_path.is_file():
        raise WheelhouseError(f"no {INDEX_NAME} in {wheelhouse}; fill the wheelhouse first")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    present = {p.name for p in Path(wheelhouse).iterdir()}
    return [f for f in index.get("files", []) if f not in present]
