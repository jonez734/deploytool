# one deploytool writer — deploytool

Every install target should have one writer. Builds run only in scratch copies, and each install target is written by one account. Today the zoid6 install is written by `jam` through `deploy`, so new files in `/home/zoid6` are `jam`-owned and the permission checks keep failing.

Done for zoid6 (zoid6 `5ceced8`): wheel builds and `install-user` stamp `_version.py` only in the scratch copy, so no checkout is written by a build.

Deferred until the sudo rule is in place: run the install as `zoid6` through a sudo rule that lets `jam` run only the deploy commands for zoid6 (`deploy zoid6.wheels`, `deploy zoid6.venv`, `sync-wheels`, `zoid6-perms.sh`).

## Open

- [ ] No checkout version step in deploytool. Its `venv` targets for other projects call those projects' Makefiles, so they inherit each project's item above. Keep the scratch-only rule in deploytool's TODO for any new target.
- [ ] Deferred: the sudo wrapper that lets `jam` run zoid6 deploys as `zoid6` (not written; waiting for the sudo rule).

## Status (current)

- zoid6 venv and dist-wheels are zoid6-owned; `scripts/zoid6-perms.sh --check` passes.
- `bin/` is locked (`0755`, owned by zoid6); the sudo rule `/etc/sudoers.d/zoid6-venv-bin` lets jam run
  `/home/zoid6/venv/bin/*` as zoid6 with a password prompt.
- `sync-wheels`, the installer (`$VENV/bin/pip`), and the build helper's `safe.directory` all run as zoid6.
- Jam keeps `deploy` for the operator steps. `bin/` is locked (`zoid6:zoid6 2755`, ACL effective `r-x`
  for group zoid6), so a jam-run `deploy zoid6.venv` used to fail partway through pip.
- Now: `run_bed_instance_venv` checks `<venv>/bin` before the installer runs. If the deploy user cannot
  write it, deploy stops with rc=2 and prints the account command, built from the registry fields:
  `sudo -u <account> <venv>/bin/deploy <name>.venv --prefix=<venv>`. The account runs that command.
  Deploytool never runs sudo itself. Tests: `tests/test_deploy_zoid6_venv.py`.
- Verified: zoid6 venv installed as zoid6 via `sudo -u zoid6 ... deploy zoid6.venv`; zoid6's and jam's
  `deploytool` both rebuilt from current source.
