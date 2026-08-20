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
| `--dry-run` | Print commands instead of running |
| `--verbose` | Verbose output (default: on) |
| `--verify` | Run post-deploy verification step |
| `--debug` | Debug mode |
| `--editable` | Install per-project Python packages in editable mode (`pip install -e`); sets `DEPLOY_EDITABLE=1` in the `make` env |

### Examples

```sh
# deploy everything for bbsengine6 (tui + www)
deploy bbsengine6

# deploy only the tui wheel for bbsengine6 and its conditional deps
deploy bbsengine6.tui

# dry-run: see the full chain without executing
deploy --dry-run bed.tui

# deploy + verify (runs bbsengine6's blurb render test after)
deploy --verify bbsengine6

# editable install across the chain: edits in any source tree are
# picked up on next interpreter start without a rebuild
deploy --editable bbsengine6.tui
deploy --editable bed
deploy --editable casino.tui

# dry-run of the editable chain (note the DEPLOY_EDITABLE=1 prefix)
deploy --dry-run --editable bbsengine6.tui

# full chain for the article2 blog
deploy article2
```

### Sub-target semantics

A bare `deploy foo` (no `.sub`) runs every entry in
`TARGETS[foo]` — e.g., `deploy bbsengine6` runs both `tui` and
`www`. `deploy foo.tui` pins a single sub.

`prod` is opt-in: it is the sudo-umbrella install for `bed` and
`zoid6` and is dropped from auto-expansion unless the caller (or a
transitive explicit dep) named it. See SPECS.md §3.2.

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
