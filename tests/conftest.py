"""Shared test helpers for deploytool.

``instance_settings`` returns the real resolved settings for a bed instance with selected fields
replaced, so a test can point one path at a temp directory without patching module internals.
"""

import pytest

from deploytool import lib


@pytest.fixture
def instance_settings(monkeypatch):
    """Return apply(name, **overrides): patch the named instance's settings and return them.

    The real loader runs for every field not overridden. Other instance names fall through to the
    real loader unchanged.
    """
    real = lib._instance_settings

    def apply(name, **overrides):
        base = real(name)
        base.update(overrides)

        def patched(n):
            return dict(base) if n == name else real(n)

        monkeypatch.setattr(lib, "_instance_settings", patched)
        return base

    return apply
