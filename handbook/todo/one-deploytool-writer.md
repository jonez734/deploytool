# one deploytool writer — deploytool

Every install target should have one writer. Builds run only in scratch copies, and each install target is written by one account. Today the zoid6 install is written by `jam` through `deploy`, so new files in `/home/zoid6` are `jam`-owned and the permission checks keep failing.

Done for zoid6 (zoid6 `5ceced8`): wheel builds and `install-user` stamp `_version.py` only in the scratch copy, so no checkout is written by a build.

Deferred until the sudo rule is in place: run the install as `zoid6` through a sudo rule that lets `jam` run only the deploy commands for zoid6 (`deploy zoid6.wheels`, `deploy zoid6.venv`, `sync-wheels`, `zoid6-perms.sh`).

## Open

- [ ] No checkout version step in deploytool. Its `venv` targets for other projects call those projects' Makefiles, so they inherit each project's item above. Keep the scratch-only rule in deploytool's TODO for any new target.
- [ ] Deferred: the sudo wrapper that lets `jam` run zoid6 deploys as `zoid6` (not written; waiting for the sudo rule).
