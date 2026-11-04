"""The shared pip command for installing a bed instance's wheels into its venv.

Every bed-instance venv is installed by one command, built here. A deployment chooses, per
instance, how external (non-internal) dependencies are supplied:

- ``index``: pip resolves them from its configured index (PyPI).
- ``wheelhouse``: pip resolves them only from a local directory, with ``--no-index``. A package
  that is not in the wheelhouse fails the install by name, and nothing is fetched.

Internal packages (bbsengine6, bed, casino, ...) always come from the instance's dist directory,
through ``--find-links``. ``--no-deps`` is never used, so a wheel's declared dependencies are
installed. ``setuptools`` is not needed in the target venv: wheels are built in an isolated
environment.
"""

from __future__ import annotations

import os
from typing import Optional, Sequence

#: The two supply modes a bed instance may use for external dependencies.
MODE_INDEX = "index"
MODE_WHEELHOUSE = "wheelhouse"
MODES = (MODE_INDEX, MODE_WHEELHOUSE)


class InstallerConfigError(ValueError):
    """Raised when an instance's installer settings are inconsistent (for example an unknown mode)."""


def check_mode(mode: str, wheelhouse: Optional[str]) -> str:
    """Return ``mode`` if it is valid for the settings, else raise :class:`InstallerConfigError`.

    ``wheelhouse`` mode needs a wheelhouse directory; ``index`` mode must not name one, so a
    deployment cannot silently mix the two.
    """
    if mode not in MODES:
        raise InstallerConfigError(f"install mode must be one of {MODES}, not {mode!r}")
    if mode == MODE_WHEELHOUSE and not wheelhouse:
        raise InstallerConfigError("install mode 'wheelhouse' needs a wheelhouse directory")
    if mode == MODE_INDEX and wheelhouse:
        raise InstallerConfigError("install mode 'index' takes no wheelhouse; set mode to 'wheelhouse'")
    return mode


def build_pip_command(
    venv: str,
    wheels: Sequence[str],
    *,
    dist: str,
    mode: str = MODE_INDEX,
    wheelhouse: Optional[str] = None,
) -> list[str]:
    """The argv that installs ``wheels`` into ``venv``.

    ``wheels`` are file names in ``dist``, in the order the manifest lists them; pip is given full
    paths so the order and the set are exact. The command never uses ``--no-deps``.

    Args:
        venv: the venv directory; its interpreter runs pip.
        wheels: wheel file names, from the instance manifest.
        dist: the directory holding the internal wheels, given to ``--find-links``.
        mode: ``index`` or ``wheelhouse``.
        wheelhouse: the external-package directory, required in ``wheelhouse`` mode.
    """
    check_mode(mode, wheelhouse)
    if not wheels:
        raise InstallerConfigError("no wheels to install")
    python = os.path.join(venv, "bin", "python")
    cmd = [
        python, "-m", "pip", "install",
        "--upgrade-strategy", "only-if-needed",
        "--find-links", dist,
    ]
    if mode == MODE_WHEELHOUSE:
        cmd += ["--no-index", "--find-links", wheelhouse]
    cmd += [os.path.join(dist, name) for name in wheels]
    return cmd


def describe_mode(mode: str, wheelhouse: Optional[str]) -> str:
    """A one-line description of the supply mode, for the deploy output."""
    if mode == MODE_WHEELHOUSE:
        return f"external dependencies from wheelhouse {wheelhouse} (no index access)"
    return "external dependencies from the package index"
