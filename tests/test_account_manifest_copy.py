"""The zoid6 account step copies the manifest with the wheels, so the installer never runs a stale one."""

import inspect

from deploytool import lib


def test_account_step_copies_the_manifest():
    src = inspect.getsource(lib.run_bed_instance_wheels)
    assert '_stage_file(s["manifest"]' in src
