# Changelog

All notable changes to deploytool are recorded here. Versions follow
`PEP 440` (`0.0.1.dev<YYYYMMDDhhmm>` for in-development builds; stable
releases bump the patch). Dates are the day the commit landed on
`main`.

## [Unreleased]

### Added
- **bbsengine6 engine-stage / engine-prod sub-targets.** Operators can
  now stage and prod-push the `bbsengine6/engine/*.php` entry-point
  install onto the zoidtechnologies.com vhost without running the
  full `bbsengine6` umbrella:
    - `deploy bbsengine6.engine-stage` runs `make deploy-engine-stage`
      → `make -C engine stage`, which rsyncs the PHP files locally to
      `/srv/www/vhosts/zoidtechnologies.com/html/engine/`.
    - `deploy bbsengine6.engine-prod` runs `make deploy-engine-prod`
      → `make engine-deploy-prod` (the existing umbrella at
      `bbsengine6/Makefile:220-221`) which calls `make -C engine
      deploy` (stage + merlin push).
  Both subs rely on the existing `?=` defaults at
  `bbsengine6/Makefile:22-23` and `bbsengine6/engine/Makefile:2-3`;
  no per-vhost overrides are needed for the zoidtechnologies.com
  vhost. `engine-stage` / `engine-prod` are reachable via the unique
  prefixes `engine-s` / `engine-p`; bare `engine` is ambiguous and
  triggers the existing "ambiguous sub-target prefix" error.
  Existing `bbsengine6.wwworg` (bbsengine.org vhost) is unchanged
  and continues to handle its own vhost via inline `ENGINESTAGEDOCROOT`
  overrides. The unconditional `DEPENDENCIES['teos'] = ['bbsengine6',
  'zoid6']` link is unchanged — `deploy teos.www` still drives the
  bare `bbsengine6` deploy umbrella as before. Regression guard:
  `tests/test_deploy_bbsengine6_engine.py`.
- **Shortest-unique-prefix sub matching.** The sub string on the
  command line no longer needs to be the full sub name. The
  resolver accepts the shortest unique prefix within the
  project's own `TARGETS` list. `deploy bbsengine6.h`,
  `deploy bbsengine6.hand`, and `deploy bbsengine6.handbook`
  all resolve to `bbsengine6.handbook`. `deploy zoid6.p` (or
  `bed.p` / `mistermcfeely.p`) resolves to `<base>.prod`. Match
  is case-sensitive, prefix-anchored (not substring), and
  per-base scoped (a prefix that resolves in one project's
  `TARGETS` does not leak into another). Implementation lives in
  `lib.resolve_sub_prefix` (`src/deploytool/lib.py:149-184`); see
  `SPECS.md §4.1` for the full contract. Regression guard:
  `tests/test_deploy_sub_prefix.py` (24 tests).
- **Ambiguous-prefix error class.** When a sub prefix matches
  more than one entry in `TARGETS[base]` (e.g. `bbsengine6.www`
  matches both `wwworg` and `wwwcom`), the resolver exits `1`
  with a distinct "ambiguous sub-target prefix" message that
  names the candidate subs. The existing "unknown sub-target"
  message is preserved verbatim for zero-match errors (e.g.
  `bbsengine6.x`). The two error classes are intentionally
  distinct so a typo surfaces as unknown, not ambiguous.

### Changed
- `mistermcfeely` no longer installs into `/var/lib/zoid6/venv`.
  Both `deploy mistermcfeely.tui` and `deploy mistermcfeely.prod`
  now install into the operator's active venv (the `VENV_USER`
  sentinel — resolved at runtime from `$VIRTUAL_ENV` /
  `sys.prefix`). The previous shared-zoid6-venv layout is
  reversed: `mistermcfeely`'s `VENV_LAYOUT` entry
  (`src/deploytool/lib.py:73`) changed from `"/var/lib/zoid6/venv"`
  to `VENV_USER`, and `mistermcfeely/Makefile` no longer
  references `/var/lib/zoid6/venv`, `sudo -u zoid6`, or
  `VENV_DIR`/`VENV_OWNER`/`VENV_GROUP`. The split into `tui`
  (operator-side) and `prod` (sudo umbrella) remains — `prod`
  is still the only sub-target that runs `sudo` (for the FHS
  bits: sysusers, tmpfiles, systemd, `/etc/postoffice/`,
  saslauthd, pam.d), and it now writes the wheel install into
  the operator's venv (no `sudo -u zoid6`). See `SPECS.md §5.1`.
- `deploy mistermcfeely` (bare) is now **ambiguous** — the
  resolver exits 1 listing `[tui, prod]`. Previously mistermcfeely
  was bare-base (no `TARGETS` entry) and the bare invocation ran
  the umbrella `make deploy` target. Callers must now write
  `deploy mistermcfeely.tui` (operator-side, no sudo) or
  `deploy mistermcfeely.prod` (sudo umbrella install into
  `/var/lib/zoid6/venv`). Mirrors the existing bed/zoid6
  multi-sub pattern.

### Added
- `mistermcfeely` now has `[tui, prod]` sub-targets in `TARGETS`
  (`src/deploytool/lib.py:133`), so `deploy mistermcfeely.tui`
  and `deploy mistermcfeely.prod` resolve via the standard
  sub-target machinery (was bare-base before; bare invocation
  now exits 1 listing the subs, matching the bed/zoid6 pattern).
  See `SPECS.md §5.1` for the tui/prod contract.
- `mistermcfeely/Makefile`:
  - New `OUTDIR = /srv/repo/mistermcfeely/` (canonical cross-
    project OUTDIR, matching bed/casino/zoid6).
  - New `deploy-tui` target — operator-side (no sudo): builds
    bbsengine6 + mistermcfeely wheels into `$(OUTDIR)`, runs
    precheck-editable against the operator's active venv, then
    installs (editable or wheel) into the active venv and runs
    verify-install. Same shape as `casino.tui`.
  - New `deploy-prod` target — sudo umbrella alias for the
    full `install` chain (sysusers + tmpfiles + venv + systemd
    + etc), forwarding `DEPLOY_EDITABLE`/`DEPLOY_WITH_DEPS`/
    `DEPLOY_UPGRADE` to the sub-make.
  - New `build` target — operator-side wheel build, used by
    `deploy-tui` and re-invoked by `install-venv` to keep
    `$(OUTDIR)` in sync with the current source.
  - New `precheck-editable` macro — multi-package (loops over
    `WHEEL_PACKAGES := bbsengine6 mistermcfeely`), no sudo,
    reads `dist-info/direct_url.json` directly per PEP 610 to
    detect PEP 660 editable-shadow installs. Branches on
    `DEPLOY_WITH_DEPS` (hard-fail vs. warn-and-proceed).
  - New `verify-install` macro — multi-package, no sudo, reads
    `dist-info/METADATA` directly (no `pip show`), compares
    against the wheel's filename and METADATA Version.
  - The `pip install --upgrade pip` line is intentionally NOT
    gated on `DEPLOY_UPGRADE` — stale pip breaks everything
    downstream.
- `--upgrade` / `--no-upgrade` CLI flag (default: `--upgrade`). When
  enabled, deploytool sets `DEPLOY_UPGRADE=1` in the subprocess env
  so every per-project Makefile splices `--upgrade` into its
  `pip install` lines; the install replaces any prior version of the
  same distribution and pulls the newest transitive deps from PyPI.
  When `--no-upgrade` is passed, deploytool strips `DEPLOY_UPGRADE`
  from the subprocess env (mirroring the `DEPLOY_EDITABLE` /
  `DEPLOY_WITH_DEPS` / `DEPLOY_DRY_RUN` strip-on-inherit pattern),
  and per-project Makefiles fall through to the prior no-op-if-
  version-matches behavior. **Behavior change**: deploys now pass
  `--upgrade` by default, so transitive deps track their PyPI
  releases between deploys. Operators who need a hermetic deploy
  against the wheels in `$(OUTDIR)` only should pass `--no-upgrade`.
  Same env-var contract as the existing `DEPLOY_EDITABLE` /
  `DEPLOY_WITH_DEPS` / `DEPLOY_DRY_RUN` vars: literal-string
  `ifeq ($(DEPLOY_UPGRADE),1)` match — deploytool is the canonical
  writer (sets to `1` or strips entirely). See README and
  `SPECS.md §2.3`.
- Per-project Makefile wiring for `DEPLOY_UPGRADE` (each project
  declares `DEPLOY_UPGRADE ?=`, defines
  `PIP_UPGRADE_FLAG := $(if $(filter 1,$(DEPLOY_UPGRADE)),--upgrade,)`,
  and splices `$(PIP_UPGRADE_FLAG)` into every `pip install` line):
  `deploytool/Makefile`, `bbsengine6/Makefile`,
  `bbsengine6/py/src/Makefile`, `bed/Makefile`, `casino/Makefile`,
  `zoid6/src/Makefile`, `zoidoffice/src/Makefile`,
  `getdate_next/Makefile`, `yummyjam/article2/Makefile`,
  `mistermcfeely/Makefile`. The `pip install --upgrade pip` line in
  each `install-venv` block is intentionally NOT gated on
  `DEPLOY_UPGRADE` — a stale `pip` breaks everything downstream and
  is unrelated to the project wheel install.
- `test_deploy_upgrade.py` — regression coverage for the `--upgrade`
  / `--no-upgrade` flag and the `DEPLOY_UPGRADE` env-var plumbing.
  Mirrors `test_deploy_with_deps.py`: CLI parser round-trip (default
  on, `--no-upgrade` flips it), `run_make_deploy` env-var propagation
  (sets `DEPLOY_UPGRADE=1` by default, strips when `--no-upgrade` is
  passed, strips a pre-existing `DEPLOY_UPGRADE` shell var when
  `--no-upgrade` is passed), and Makefile-presence assertions that
  each per-project Makefile declares `DEPLOY_UPGRADE ?=` and splices
  `$(PIP_UPGRADE_FLAG)` into its `pip install` lines.

### Added
- `bbsengine6.handbook` sub-target — `TARGETS["bbsengine6"]`
  (`src/deploytool/lib.py:131`) gains a fourth entry: from
  `["tui", "wwworg", "wwwcom"]` to `["tui", "wwworg",
  "wwwcom", "handbook"]`. `deploy bbsengine6.handbook`
  resolves to `make -C bbsengine6 deploy-handbook`, which
  stages the handbook tree and pushes the org site (the
  `wwworg` rsync chain). The bbsengine6 entry has no
  `DEPENDENCIES`, so `--with-deps` is unchanged. The
  bbsengine6 side (handler rewrite + shared
  `\bbsengine6\markdown` primitive) is committed in the
  inner `bbsengine6/` repo; the deploytool side is the
  TARGETS addition only. Regression tests:
  `tests/test_deploy_bbsengine6_www.py` updated to
  assert the four-sub shape and add four sibling
  tests mirroring wwworg/wwwcom for the handbook.

### Added
- `VERIFY_INSTALL` Makefile variable in `Makefile`, wired into the
  non-editable branch of the `install` target via `@$(VERIFY_INSTALL)`
  (after `$(PIP) install --no-deps $(WHEEL)`). Mirrors the reference
  implementation in `zoidoffice/src/Makefile`: extracts the expected
  `Version` from the wheel's filename (regex) and from `unzip -p
  $(WHEEL) '*/METADATA'`, runs `$(PIP) show $(PROJECT)`, and asserts
  all three agree. On mismatch, prints the verbatim `pip show` output
  (stdout) and aborts with a summary on stderr (`exit 1`). Catches
  the silent-no-op case where `pip install <wheel>` exits 0 without
  actually replacing an existing install (different venv,
  orphaned .dist-info, permission-denied mid-install, etc.). The
  editable branch (`DEPLOY_EDITABLE=1`) installs from source, not a
  wheel, so it skips this check — `pip show` for an editable install
  reports the source-tree version, not a wheel version, and the
  comparison semantics differ. See README and `SPECS.md`.
- `bbsengine6.wwworg` and `bbsengine6.wwwcom` sub-targets. The
  `bbsengine6/Makefile` defines matching `deploy-wwworg` /
  `deploy-wwwcom` wrapper rules that delegate to the existing
  `wwworg:` / `wwwcom:` targets (which in turn drive
  `bbsengine6/www/{org,com}/Makefile`). Bare `deploy bbsengine6`
  is now ambiguous across three subs (`tui`, `wwworg`, `wwwcom`).
- `test_deploy_bbsengine6_www.py` — regression coverage mirroring
  `test_deploy_zoidoffice.py`: TARGETS shape (three subs, legacy
  `www` removed), bare-invocation ambiguity (default and
  `--with-deps`), explicit-sub resolution for each of the three
  subs, legacy `www` rejection, make-target wiring
  (`deploy-wwworg` / `deploy-wwwcom`), and Makefile-level
  presence of the wrapper rules plus their `wwworg:` / `wwwcom:`
  delegate targets. Plus two `templates_c`-handling assertions:
  the www push rsyncs must `--exclude "templates_c"` and
  `--chmod=Dg+rwxs`, and the per-sub `stage` targets must keep
  their `mkdir .../templates_c/` plus a `.gitkeep` sentinel.
- `--with-deps` CLI flag (default `false`). When set, the resolver
  walks transitive dependencies for every requested project. When
  unset (the default), only the projects the caller explicitly
  named run — no transitive dep walking. Combined with `--editable`,
  installs each package editable from the source tree. See README
  and `SPECS.md §2.2`.
- `test_deploy_with_deps.py` — regression coverage for the
  `--with-deps` flag and the bare-base ambiguity rules. Includes
  bare `casino`/`bed`/`multi-project` listing-then-exit (under
  both `--with-deps` and the default), single-sub auto-pick,
  explicit-sub chain walking under `--with-deps`, and CLI parser
  round-trips.
- `test_deploy_shadow_install.py` — end-to-end regression
  coverage for the PEP 660 editable-installer shadow on
  `deploy bbsengine6.tui`. Pins all four contracts: precheck
  hard-fail under the default (no `--with-deps`), precheck
  warn-and-proceed under `--with-deps`, the
  `verify-install`-catches-the-shadow correctness check that
  only fires under `--with-deps`, and the negative control
  (no editable install, clean deploy). Catches the regression
  that drops `$(verify-install)` from
  `bbsengine6/py/src/Makefile:186-187` or removes the
  `DEPLOY_WITH_DEPS` env-var plumbing in
  `lib.run_make_deploy`. See `SPECS.md §2.2.1.1`.

### Changed
- `TARGETS['bbsengine6']` changed from `['tui', 'www']` to
  `['tui', 'wwworg', 'wwwcom']`. The legacy `www` sub (which
  deployed the engine library via `php-deploy` + smarty rsync)
  is removed; callers must use `wwworg` / `wwwcom` for the
  website deploys. The `bbsengine6/Makefile` `deploy-www` rule
  is removed and the corresponding `.PHONY` entry updated to
  list `deploy-wwworg` / `deploy-wwwcom` instead. The legacy
  `wwwcom:` rule that was commented out (`#wwwcom:`) is now
  uncommented and active alongside `wwworg:`.

### Changed
- `--with-deps` no longer auto-expands bare-base invocation to all
  subs. Previously `deploy --with-deps casino` ran both
  `casino.tui` and `casino.www` (and their full dep chains); now
  bare-base is ambiguous whenever `TARGETS[foo]` has more than one
  entry, regardless of `--with-deps`. The resolver lists the subs
  and exits `1`; callers must name them explicitly
  (`deploy --with-deps casino.tui casino.www`). `--with-deps`
  now controls a single behavior: transitive-dep walking. The
  previous "build the whole thing" shortcut for bare-base under
  `--with-deps` is gone; the flag is documented as such in
  `SPECS.md §2.2` and the `--with-deps` argparse help text. The
  `prod` opt-in (§3.2) is unchanged: `prod` survives only when
  the caller (or a transitive explicit dep) named it.

### Changed
- `--dry-run` now passes `--dry-run` through to each `make` invocation
  (appended after the target) and exports `DEPLOY_DRY_RUN=1` in the
  subprocess env, instead of short-circuiting in deploytool. Per-project
  Makefile dry-run output (e.g. the inner `pip install ...` recipe
  lines, recursive `make -C zoid6/src deploy-tui` invocations, etc.)
  is captured and printed via the existing stdout-echo path in
  `lib.run_make_deploy`. `make -n` failures still abort the deploy
  via `DeployFailed(rc, label)`. The verify step (`--verify` ->
  `php test_blurb_render.php`) keeps its short-circuit under
  `--dry-run` since `php` has no dry-run flag. `DEPLOY_DRY_RUN` is
  stripped from the subprocess env when `--dry-run` is not passed
  (same single-source-of-truth pattern as `DEPLOY_EDITABLE`). The
  test `test_run_make_deploy_dry_run_does_not_invoke_subprocess`
  is rewritten to assert the new contract; new tests
  `test_run_make_deploy_dry_run_strips_env_var_when_not_set` and
  `test_run_make_deploy_dry_run_aborts_on_nonzero_rc` cover env-var
  propagation/strip and dry-run failure propagation respectively.
  See `SPECS.md §2` and `§2.1.1`.
- Bare-project invocation semantics (`deploy foo` with no `.sub`)
  are now **ambiguous** when `TARGETS[foo]` has more than one
  entry: the resolver lists the available sub-targets and exits
  `1`. The previous behavior (auto-expanding every sub in
  `TARGETS[foo]`) was removed. Callers must now specify
  sub-targets explicitly (`deploy bbsengine6.tui bbsengine6.www`)
  or pass `--with-deps` to opt into the "build the whole thing"
  auto-expand.
- `lib.resolve(projects, with_deps=False)` — added `with_deps`
  kwarg. Default `False` preserves the new bare-no-ambiguity
  semantics. `main.main()` (`src/deploytool/main.py:19`) passes
  `args.with_deps` through. The dep walker (`visit()` at
  `lib.py:310-348`) skips both `DEPENDENCIES` and
  `CONDITIONAL_DEPENDENCIES` walks when `with_deps` is False.
- `SPECS.md` — design specs extracted from `src/deploytool/lib.py`,
  with cross-references to specific line ranges for each registry
  (CLI flags, dependency graph, sub-targets, make aliases, venv
  registry, project dir resolution, test coverage, out-of-scope).
- `README.md` — install (wheel + editable), usage examples
  (`deploy bbsengine6`, `deploy bed.tui`, `--dry-run`, `--verify`),
  build/publish flow, test entry point, and architecture pointers
  to `lib.py` registries.
- `CHANGELOG.md` — this file.
- `make test` target — runs `pytest tests/`.
- `--editable` CLI flag — installs per-project Python packages in
  editable mode (`pip install -e`) instead of from a freshly-built
  wheel. Sets `DEPLOY_EDITABLE=1` in the `make` invocation's
  environment; each per-project Makefile can swap wheel install for
  editable install. Independent of `OUTDIR`: editable install uses
  the source tree, not `/srv/repo/<project>/`.

### Changed
- Repo is now standalone: `deploytool/` has its own `.git/` and
  `origin` points at `git@github.com:jonez734/deploytool.git`. Was
  previously tracked as part of the parent monorepo at
  `/home/opencode/data/work/`. The parent now lists `deploytool/` in
  its `.gitignore` alongside the sibling standalone subdirs.
- `.gitignore`: `*.egg-info` → `*.egg-info/` so the directory itself
  is ignored (not just files named that pattern).
- `TODO.md`: added a "Repo status" block at the top documenting the
  standalone-repo milestone, the parent monorepo relationship, and
  pointers to the in-tree and parent repos.
- `--editable` flag is now the sole source of truth for editable
  install mode. When `--editable` is **not** passed, deploytool
  strips `DEPLOY_EDITABLE`, `EDITABLE`, and `DEV` from the
  subprocess env before invoking `make` so an operator who happens
  to have one of those vars set in their shell does not silently
  trigger editable mode. With `--editable`, deploytool explicitly
  sets `DEPLOY_EDITABLE=1` in the subprocess env.
- `run_make_deploy` and `run_verify` now raise
  `deploytool.lib.DeployFailed(rc, label)` on any non-zero subprocess
  exit, subprocess timeout, or environment error (was: log-and-continue
  in `run_verify`; log-and-return-rc in `run_make_deploy`). `main.main()`
  catches the exception and returns 1 with a structured abort message.
  The chain still stops at the failing project; verify failures no
  longer silently report `deploy complete`.
- Both `run_make_deploy` and `run_verify` are hardened: explicit
  `encoding="utf-8"`, `errors="replace"`, `timeout=--timeout` (default
  600s), `start_new_session=True`; narrow exception handling that
  propagates `KeyboardInterrupt` and `SystemExit` instead of
  swallowing them; structured error messages that include the failing
  command and (for verify) cwd.
- `--verbose` CLI flag removed. `run_make_deploy` always captures
  stdout/stderr and prints stdout on success, stderr on failure. The
  flag was the only consumer of `args.verbose`; the removal is safe.
- `--timeout SECONDS` CLI flag added (default
  `DEFAULT_TIMEOUT_SECONDS` = 600s). Per-step subprocess timeout;
  timeout expiry raises `DeployFailed(rc=-1, label)`.

## [0.0.1.dev20260820] — 2026-08-20

Initial standalone-repo publication. The implementation, tests, and
Makefile scaffolding were in place before the repo was split out;
this is the first commit set under the standalone repo.

### Added
- `Makefile` — `version`, `build`, `install`, `deploy-tui`,
  `install-venv`, `uninstall-venv`, `clean` targets. Builds via
  `python -m build`; wheels land in `./dist/`.
- `src/deploytool/__main__.py` — CLI entry point
  (`deploy = deploytool.__main__:main`).
- `src/deploytool/main.py` — groups subs by base project for display.
- `src/deploytool/lib.py` — topo-sort dependency resolver and the
  registries it consults (`DEPENDENCIES`,
  `CONDITIONAL_DEPENDENCIES`, `TARGETS`, `MAKE_TARGET_ALIASES`,
  `ALIASES`, `ALIAS_PATTERNS`, `VENV_LAYOUT`, `VENV_USER`,
  `PROJECT_DIRS`).
- `src/deploytool/_version.py` — generated by `make version`.
- `src/pyproject.toml` — python `>=3.9,<3.14`, runtime dep on
  `bbsengine6`, optional `[dev]` extras (`pytest>=8.0`), console
  script `deploy`.
- `tests/test_deploy_bed_tui.py` — regression guard for the
  egg-info absolute-path trap and the `bed.tui` →
  `deploy-venv` resolution path.
- `tests/test_deploy_getdate_next_tui.py` — regression guard for
  `PREPARE_BUILD` invariants (foreign-owned `build/` chmod EPERM;
  `chmod 1775` not `chmod g-s`).
- `TODO.md` — completed items (default sub-target semantics, the
  `resolve()` multi-sub fix), open `VENV_LAYOUT` cleanup, Phase 0
  (wheel output to `/srv/repo/<project>/`), Phase 1 (`deploy
  --dev` editable install).
- `deploy.sh` — one-off blurb double-render fix used during a
  specific deploy; flagged as out-of-scope for the deploytool
  registry in `SPECS.md §10`.
- `.gitignore` — `*.egg-info/`, `dist/`, `__pycache__/`, `.venv/`,
  `build/`, `.pytest_cache/`, `.ruff_cache/`.
