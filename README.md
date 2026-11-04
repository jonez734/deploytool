# deploytool

A Python CLI that orchestrates `make` invocations across the
zoidtechnologies.com project tree. It resolves a `deploy <project>`
request into a topologically sorted chain of `make deploy-<sub>` calls
and runs them in order, stopping at the first failure. Bed-instance
installs (`<name>.wheels`, `<name>.venv`) run through deploytool's own
code, not make.

- **Repo:** https://github.com/jonez734/deploytool
- **Spec:** [SPECS.md](SPECS.md)
- **Status:** [TODO.md](TODO.md)
- **History:** [CHANGELOG.md](CHANGELOG.md)

## Install

`deploytool` installs as a wheel into the active venv, or editable from
the source tree:

```sh
make install                    # build the wheel into ./dist and pip-install it
make install DEPLOY_EDITABLE=1  # editable install from the source tree
pip install -e .                # equivalent to DEPLOY_EDITABLE=1
```

Requires Python `>=3.9,<3.14` (`src/pyproject.toml`). The cap at 3.14 is
deliberate: asimov depends on `mediapipe`, which does not support newer
Python. Do not raise it without checking that dependency.

Runtime dependency: `bbsengine6`, resolved by `pip`.

## Usage

```sh
deploy [options] project[.sub] [project[.sub] ...]
```

| Flag | Effect |
|---|---|
| `--host HOST` | Target host (default: `merlin`). |
| `--dry-run` | Pass `--dry-run` to each `make` (sets `DEPLOY_DRY_RUN=1`) and print what would run. Bed-instance steps print the command and do not run it. The venv bin guard and the verify step do not run. |
| `--timeout SECONDS` | Per-step timeout (default: `600`). An expired timeout aborts the deploy. |
| `--verify` | Run the post-deploy verify step. Only `bbsengine6` has one (`php test_blurb_render.php`); other projects ignore the flag. Skipped under `--dry-run`. |
| `--debug` | Debug output. |
| `--editable` | Install Python packages in editable mode. Sets `DEPLOY_EDITABLE=1`. |
| `--with-deps` | Include transitive dependencies. Without it, only the named projects run. |
| `--prefix PATH` | Venv install prefix for `<project>.venv` and `<project>.prod`. Passed to make as `DEPLOY_PREFIX`. Without it, the project's registered venv (`VENV_LAYOUT`) is used. A stale `DEPLOY_PREFIX` in your shell is removed. |
| `--upgrade` / `--no-upgrade` | Add `--upgrade` to every `pip install` in the chain (default: on). `--no-upgrade` installs only from the wheels in `$(OUTDIR)`. |

### Examples

```sh
# build only what was named (no bbsengine6, no bed pulled in)
deploy casino.venv

# several subs at once, no transitive deps
deploy casino.venv casino.www

# a bare base with several subs is ambiguous: names the subs and exits 1
deploy casino
deploy --with-deps casino          # still ambiguous; name the subs

# explicit sub with deps: the chain for that sub
deploy --with-deps casino.venv     # -> bbsengine6 (bare), casino.venv

# preview: runs make -n for each step; skips the venv bin guard and verify
deploy --dry-run casino.venv

# deploy and verify (bbsengine6 is the only project with a verify step)
deploy --verify bbsengine6.www

# editable install across the chain
deploy --editable --with-deps casino.venv

# single-sub project: no ambiguity
deploy getdate_next                # -> getdate_next.tui

# project with no TARGETS: the bare make `deploy` target runs
deploy mistermcfeely

# bbsengine6 website and engine deploys
deploy bbsengine6.wwworg
deploy bbsengine6.wwwcom
deploy bbsengine6.prod             # the engine-library umbrella
deploy bbsengine6.engine-stage     # local rsync only
deploy bbsengine6.engine-prod      # merlin push of the staged engine

# sub prefixes: the shortest unique prefix within TARGETS is accepted
deploy bbsengine6.handbook
deploy bbsengine6.hand
deploy bbsengine6.h
deploy zoid6.p                     # -> zoid6.prod
deploy bed.p                       # -> bed.prod

# an ambiguous prefix errors and names the candidates
deploy bbsengine6.www              # matches both wwworg and wwwcom
```

### Bed-instance deploys

Bed instances are registered in `src/deploytool/bed_instances.json`. Each
entry names the account that owns the install, the group that may write
it, the venv, the installer, and the staged wheel list. Deploytool reads
the registry, and nothing in the code names a specific account.

Two sub-targets run through deploytool itself:

- **`<name>.wheels`** builds the instance's wheels into the staging
  directory and copies them to the account's `dist-wheels`. It needs
  write access to the account's dist directory.
- **`<name>.venv`** runs the account's installer against the staged
  wheels and the venv. Before pip runs, it checks that the venv and its
  `bin/` are writable by the deploy user. If not, it stops with rc `2`
  and prints the command the owning account should run, for example:

  ```
  sudo -u zoid6 /home/zoid6/venv/bin/deploy zoid6.venv --prefix=/home/zoid6/venv
  ```

  Deploytool never runs sudo itself. The owning account runs the printed
  command.

Other projects' `venv` and `prod` subs also check `<prefix>/bin` before
make runs (`_check_venv_bin_writable`). pip replaces console-script
launchers in `bin/`. When another account owns that directory, pip can
uninstall a launcher and then fail to restore it, which leaves the venv
partly changed. The check stops the deploy before that can happen. Dry
runs are not checked.

### Sub-target semantics

`TARGETS[proj]` lists the subs a project exposes. A project can be
invoked in four ways:

- **`deploy proj.sub`** runs the named subs. Dependencies are not pulled
  in unless `--with-deps` is set.
- **`deploy proj`** (bare) is ambiguous when `TARGETS[proj]` has more than
  one entry. It lists the subs and exits `1`.
- **`deploy --with-deps proj`** (bare) expands to every entry in
  `TARGETS[proj]` and walks the full dependency chain.
- **No `TARGETS[proj]`** (for example `mistermcfeely`): the bare make
  `deploy` target runs.

Single-entry `TARGETS` (for example `getdate_next -> ["tui"]`) run that
one sub when called bare.

`--with-deps` controls the dependency chain. Without it, only the named
projects run. With it, every requested sub's dependencies run first, in
topological order.

## Build & publish

```sh
make version           # stamps src/deploytool/_version.py
make build             # sdist + wheel into ./dist/
make install           # build + pip install into the active venv
make test              # pytest tests/
make clean             # remove build/, dist/, egg-info, __pycache__
```

Output goes to `./dist/`. Deploytool is a standalone repo, so its `OUTDIR`
is `dist/`, not `/srv/repo/deploytool/`.

## Tests

```sh
make test
# or
PYTHONPATH=src pytest tests/
```

`PYTHONPATH=src` makes the tests import the checked-out code, not an
installed copy. Some tests call `make` against the sibling project
Makefiles under `SOURCE_BASE` (`DEPLOYTOOL_SOURCE_BASE`, default
`/home/opencode/data/work`). On a checkout without those trees, those tests
are skipped.

The tests are regression guards for failures that broke real deploys.
Notable files:

- `test_deploy_bed_instances.py`, `test_deploy_zoid6_venv.py`,
  `test_deploy_zoid6_root.py`, `test_deploy_zoid6_shared.py`: bed-instance
  wheel and venv steps, the zoid6 path, and the installer contract.
- `test_deploy_venv_bin_guard.py`: the `bin/` writability guard, including
  that dry runs are not checked and non-venv subs are not stopped.
- `test_deploy_prefix_flag.py`: `--prefix` and `DEPLOY_PREFIX` routing.
  These tests skip the live `bin/` check, which has its own tests.
- `test_deploy_bed_tui.py`: the `PREPARE_BUILD` build-dir mode and the
  `bed.tui` to `deploy-venv` mapping.
- `test_deploy_bbsengine6_www.py`, `test_deploy_bbsengine6_engine.py`,
  `test_deploy_bbsengine6_prod.py`, `test_deploy_bbsengine6_venv.py`:
  the `bbsengine6` sub list, the engine stage/prod split, the umbrella
  `prod`, and the `venv` target.
- `test_deploy_with_deps.py`: the `--with-deps` chain and bare-base
  ambiguity rules.
- `test_deploy_aborts_on_step_failure.py`: the `DeployFailed` contract, env
  handling, and abort propagation.
- `test_venv_layout_projects.py`: the `VENV_LAYOUT` registry.

## Architecture

The registries are plain Python dicts in `src/deploytool/lib.py`:

- `DEPENDENCIES`, `CONDITIONAL_DEPENDENCIES`: the dependency graph.
- `BARE_DEPS_SKIPPED_FOR`: `(project, sub)` pairs that do not pull a bare
  dependency. Currently `bed.venv`, `zoid6.venv`, `letteredolive.venv`,
  `aolbonics.venv`.
- `TARGETS`: the subs each project exposes.
- `MAKE_TARGET_ALIASES`: sub name to make target (for example `bed.tui`
  maps to `deploy-venv`).
- `ALIASES`, `ALIAS_PATTERNS`: user-facing names to canonical names.
- `VENV_LAYOUT`, `VENV_USER`: each project's registered venv. For the
  `venv` and `prod` subs, a non-`None` entry sets `DEPLOY_PREFIX` when
  `--prefix` is not given. `None` (`VENV_USER`) leaves the Makefile's
  default.
- `PROJECT_DIRS`: projects whose source tree is outside `SOURCE_BASE/<name>`.
- `BED_INSTANCES`: loaded from `src/deploytool/bed_instances.json`. Drives
  the `<name>.wheels` and `<name>.venv` steps.

See [SPECS.md](SPECS.md) for the design rules and their reasons.

## License

GPL-2.0-or-later. See `src/pyproject.toml` for the SPDX identifier.
