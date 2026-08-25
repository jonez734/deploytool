# Changelog

All notable changes to deploytool are recorded here. Versions follow
`PEP 440` (`0.0.1.dev<YYYYMMDDhhmm>` for in-development builds; stable
releases bump the patch). Dates are the day the commit landed on
`main`.

## [Unreleased]

### Added
- `--with-deps` CLI flag (default `false`). When set, the resolver
  walks transitive dependencies for every requested project AND
  bare-base invocation (`deploy foo` with no `.sub`) auto-expands
  to every entry in `TARGETS[foo]`. When unset (the default), only
  the projects the caller explicitly named run — no transitive
  dep walking. Combined with `--editable`, installs each package
  editable from the source tree. See README and `SPECS.md §2.2`.
- `test_deploy_with_deps.py` — regression coverage for the
  `--with-deps` flag and the bare-base ambiguity rules. Includes
  bare `casino`/`bed`/`multi-project` listing-then-exit,
  single-sub auto-pick, full-chain expansion under `--with-deps`,
  and CLI parser round-trips.

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
