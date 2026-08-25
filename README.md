# deploytool

A Python CLI that orchestrates `make` invocations across the
zoidtechnologies.com project tree. Resolves a `deploy <project>`
request into a topologically-sorted chain of `make deploy-<sub>`
calls and walks them, reporting failures.

- **Repo:** https://github.com/jonez734/deploytool
- **Spec:** [SPECS.md](SPECS.md)
- **Status:** [TODO.md](TODO.md) — Phase 1 (`--editable` flag,
  `DEPLOY_EDITABLE` env var, per-project wheel/editable swap) is
  complete. Phase 2 (zoidoffice, getdate_next, backuptools) is
  open work.

## Install

`deploytool` is consumed as a wheel from PyPI-style local installs
(via `pip install` into an active venv) or as an editable install
from the source tree. The build target also honors
`DEPLOY_EDITABLE=1`:

```sh
# from the source tree
make install                 # builds the wheel into ./dist and pip-installs it
make install DEPLOY_EDITABLE=1  # editable install from the source tree
# or, for dev (equivalent to DEPLOY_EDITABLE=1):
pip install -e .
```

Runtime dep: `bbsengine6` (resolved by `pip` automatically).

## Usage

```sh
deploy [options] project[.sub] [project[.sub] ...]
```

| Flag | Effect |
|---|---|
| `--host HOST` | Target host (default: `merlin`) |
| `--dry-run` | Pass `--dry-run` through to each `make` invocation; per-project Makefile dry-run output (e.g. inner `pip install ...` recipe lines) is captured and printed. Exports `DEPLOY_DRY_RUN=1` in the subprocess env. The verify step is skipped under `--dry-run`. |
| `--timeout SECONDS` | Per-step subprocess timeout (default: `600`); expired timeouts abort the deploy |
| `--verify` | Run post-deploy verification step |
| `--debug` | Debug mode |
| `--editable` | Install per-project Python packages in editable mode (`pip install -e`); sets `DEPLOY_EDITABLE=1` in the `make` env |
| `--with-deps` | Include transitive dependencies in the chain. Without it, only explicitly named projects are built (default: `false`). Bare bases (no `.sub`) under `--with-deps` also auto-expand to all subs. Bare bases without `--with-deps` list the available subs and exit `1`. |

### Examples

```sh
# build only what was named: casino.tui (no bbsengine6, no bed pulled in)
deploy casino.tui

# both subs for casino, no transitive deps
deploy casino.tui casino.www

# bare base is AMBIGUOUS without --with-deps: errors out listing subs
deploy casino
# -> exit 1 with: casino has multiple sub-targets (tui, www); choose ...

# bare base with --with-deps is the "build the whole thing" shortcut:
# auto-expands subs AND walks the full dep chain
deploy --with-deps casino
# -> bbsengine6.tui, bbsengine6.www, bed.tui, casino.tui, casino.www

# explicit sub under --with-deps: chain for that sub
deploy --with-deps casino.tui
# -> bbsengine6.tui, bed.tui, casino.tui

# dry-run: see the chain without executing. Each step runs `make -n`
# against the real per-project Makefile, so the output includes the
# inner recipe (e.g. `pip install /srv/repo/casino/casino-*.whl`,
# `cd py && pip install -e .` under --editable, recursive `make -C
# zoid6/src deploy-tui`, etc.). The verify step is skipped since
# `php` has no dry-run flag.
deploy --dry-run casino.tui

# deploy + verify (runs bbsengine6's blurb render test after)
deploy --verify bbsengine6.www

# editable install across the chain: edits in any source tree are
# picked up on next interpreter start without a rebuild
deploy --editable --with-deps casino.tui

# single-sub project has no ambiguity: `deploy getdate_next` -> tui
deploy getdate_next

# bare project (no TARGETS) runs unconditionally
deploy mistermcfeely
```

### Sub-target semantics

For each project, `TARGETS[proj]` lists the sub-targets that project
exposes (e.g. `casino -> ["tui", "www"]`). The caller may invoke a
project three ways:

- **`deploy proj.tui`** — pin one or more explicit subs; only those
  subs run. No transitive deps are pulled in (add `--with-deps` to
  pull them).
- **`deploy proj`** (bare, no `--with-deps`) — ambiguous if
  `len(TARGETS[proj]) > 1`. The resolver lists the available subs
  and exits `1`. Caller must name a sub (or pass `--with-deps`).
- **`deploy --with-deps proj`** (bare, `--with-deps` set) — auto-
  expands to every entry in `TARGETS[proj]` AND walks the full
  transitive dep chain. This is the one-shot "build everything
  for this project" shortcut.
- **Single-entry `TARGETS[proj]`** (e.g. `getdate_next -> ["tui"]`)
  has no ambiguity to begin with; `deploy getdate_next` (bare) runs
  `getdate_next.tui` automatically.
- **No `TARGETS[proj]`** (e.g. `mistermcfeely`, `asimov`,
  `letteredolive`) — no subs to choose; the bare `make deploy`
  target runs.

`--with-deps` controls whether the transitive dep chain (`bbsengine6`,
`bed`, etc.) is walked:

- **Default (`--with-deps` not set)** — no deps pulled. Only the
  caller-named projects run.
- **`--with-deps` set** — full topo-sorted dep chain for every
  requested sub. Combined with `--editable`, installs each package
  editable into the active venv.

## Build & publish

```sh
make version           # stamps src/deploytool/_version.py
make build             # sdist + wheel into ./dist/
make install           # build + pip install into the active venv
make test              # run pytest tests/
make clean             # wipe build/ dist/ *.egg-info/ __pycache__/
```

Output lands in `./dist/` per-project. (deploytool's local
`OUTDIR` is `dist/`, **not** `/srv/repo/deploytool/` —
deploytool is a standalone repo and publishes to PyPI from
`dist/`. The other projects Phase-0'd to `/srv/repo/<project>/`
because they share an OUTDIR with their sibling repos on the
host.)

## Tests

```sh
make test
# or directly:
pytest tests/
```

Tests are regression guards for failure modes that bit production
deploys:

- `test_deploy_bed_tui.py` — egg-info absolute-path trap;
  bed.tui → `deploy-venv` resolution; bbsengine6.tui conditional dep.
- `test_deploy_getdate_next_tui.py` — `PREPARE_BUILD` invariants
  (foreign-owned `build/` chmod EPERM; `chmod 1775` not `chmod g-s`).
- `test_deploy_with_deps.py` — `--with-deps` flag and bare-base
  ambiguity rules (multi-sub TARGETS lists subs and exits 1;
  single-sub TARGETS auto-picks; bare under `--with-deps` auto-
  expands subs and walks dep chains).
- `test_deploy_aborts_on_step_failure.py` — `run_make_deploy` /
  `run_verify` exception contract (`DeployFailed`), env handling
  (`--editable` set/strip), subprocess hardening, abort propagation
  in `main.main()`.

Tests invoke `make` against real sibling-project Makefiles under
`SOURCE_BASE` (`/home/opencode/data/work`). CI or a fresh checkout
without the sibling trees will skip them.

## Architecture

The dependency graph, target registry, sub-target aliases, venv
registry, and project directory overrides live as plain Python dicts
in `src/deploytool/lib.py`:

- `DEPENDENCIES`, `CONDITIONAL_DEPENDENCIES` — the topo graph
- `TARGETS` — sub-targets each project exposes
- `MAKE_TARGET_ALIASES` — sub name → make target name (e.g.,
  `bed.tui` → `deploy-venv`)
- `ALIASES`, `ALIAS_PATTERNS` — user-facing → canonical name map
- `VENV_LAYOUT`, `VENV_USER` — informational claims about per-project
  venv paths (registry only; Makefiles do the actual targeting)
- `PROJECT_DIRS` — projects whose source tree lives outside
  `SOURCE_BASE/<name>`

See [SPECS.md](SPECS.md) for the design rules these registries
encode, with cross-references to specific line ranges in `lib.py`.

## License

GPL-2.0-or-later. See `pyproject.toml` for the SPDX identifier.
