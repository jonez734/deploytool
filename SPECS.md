# deploytool — Specs

Design specifications for `deploytool`. The implementation lives in
`src/deploytool/lib.py`; this document is the human-readable spec it
encodes. Cross-reference line ranges so changes to the implementation
can be checked against the spec.

## 1. Purpose

`deploytool` is a thin Python CLI that orchestrates `make` invocations
across a set of sibling projects under `SOURCE_BASE` (currently
`/home/opencode/data/work`). Each project has its own Makefile with
`deploy` and/or `deploy-<sub>` targets; `deploytool` resolves the
caller's request into a topologically-sorted list of `make` calls,
walks the list, and reports failures.

## 2. CLI

```
deploy [options] project[.sub] [project[.sub] ...]
```

| Flag | Effect |
|---|---|
| `--host HOST` | Target host for ssh-based deploys (default: `merlin`) |
| `--dry-run` | Print commands instead of executing |
| `--verbose` | Verbose output (default: on) |
| `--verify` | Run post-deploy verification step after the deploy chain |
| `--debug` | Debug mode |

A bare `deploy foo` (no sub-target) runs every entry in
`TARGETS[foo]`, not just the first. `deploy foo.tui` pins a single sub.

## 3. Dependency graph

Encoded in `lib.py:21-39` (`DEPENDENCIES`) and
`lib.py:85-104` (`CONDITIONAL_DEPENDENCIES`). Rules:

1. `DEPENDENCIES[base]` — unconditional transitive deps; resolved with
   no sub-target.
2. `CONDITIONAL_DEPENDENCIES[base][cond_sub]` — extra deps pulled in
   only when the caller (or a transitive explicit dep) requested
   `cond_sub` on `base`. Values may be `(name, sub)` tuples or plain
   `name` strings; the latter match down the chain with no sub.
3. The chain is seeded once per requested `(base, sub)` pair, then
   walked topologically. The walker passes through both
   `DEPENDENCIES` and `CONDITIONAL_DEPENDENCIES` for each visited
   node.

### 3.1 Sub-target dedup

A single `deploy` call that requests the same base with multiple subs
expands each sub into its own walker seed. Two subs that alias to the
same `deploy-*` make target (see §5) collapse to one `make` invocation
in the final order.

### 3.2 `prod` opt-in

`prod` is a sudo-umbrella install for `bed` and `zoid6` and must not
run by default. `lib.py:300-301` drops auto-expanded `prod` entries
from the final order; only `prod` subs the caller (or a transitive
explicit dep) named explicitly survive.

## 4. Sub-targets

Encoded in `lib.py:106-118` (`TARGETS`). A bare sub is `[None]`,
meaning "no `deploy-<sub>` suffix; run the project's bare `deploy`
target." Projects with an entry in `TARGETS` get all listed subs
auto-expanded when the caller asks for the bare base.

Sub names are user-facing. The actual `make` target name may differ —
see §5.

## 5. Make target aliases

Encoded in `lib.py:123-126` (`MAKE_TARGET_ALIASES`). Maps a
`(project, sub)` pair to the `deploy-<sub>` make target name to run
when the user requested that sub. Applied by `run_make_deploy`
(`lib.py:312-336`) before constructing the cmd vector. Currently:

- `("bed", "tui")` → `"venv"` — `bed` has no `deploy-tui` target;
  its `tui` is a Python venv install.
- `("getdate_next", "tui")` → `"venv"` — same reason.

Bare projects (sub is `None`) get `deploy` as the make target.

## 6. Aliases

Encoded in `lib.py:41-43` (`ALIASES`) and `lib.py:45-47`
(`ALIAS_PATTERNS`). A user-facing project name that should be
canonicalized before any other processing. Pattern-based aliases
apply first; literal aliases second.

## 7. Venv registry

Encoded in `lib.py:49-70` (`VENV_USER`, `VENV_LAYOUT`).
`get_venv_layout` (`lib.py:133-147`) resolves a project's venv:

1. Apply `ALIASES` to canonicalize the project name.
2. Look up `VENV_LAYOUT[canonical]`.
3. If the value is a non-`None` string, return it. This is a CLAIM
   about what the project's Makefile does on `deploy` — deploytool
   does not plumb venv vars into `make`. Per-project Makefile
   defaults and `pip` handle venv targeting.
4. If the value is `None` (the `VENV_USER` sentinel), resolve at
   runtime: `$VIRTUAL_ENV`, else `sys.prefix` if a venv is active,
   else error and exit.

A claim entry that does NOT match what the project's Makefile
actually does is a bug — see TODO.md entries for the six
`/var/lib/zoid6/venv` claims that should be `VENV_USER` and the
two sub-target-aware entries that should be removed entirely.

## 8. Project directory resolution

`PROJECT_DIRS` (`lib.py:17-19`) lists projects whose source tree
lives somewhere other than `SOURCE_BASE/<name>`. Currently only
`article2` (which lives under `yummyjam/`). `run_make_deploy`
applies the override at cmd-construction time.

## 9. Test coverage

Tests live in `tests/` and run via `make test` (see Makefile). Each
test is a regression guard for a specific failure mode that bit
production deploys in the past:

- `test_deploy_bed_tui.py` — egg-info absolute-path trap; bed.tui →
  `deploy-venv` resolution; bbsengine6.tui conditional dep.
- `test_deploy_getdate_next_tui.py` — `PREPARE_BUILD` invariants
  (foreign-owned `build/` chmod EPERM; `chmod 1775` not `chmod g-s`).

Tests invoke `make` against real sibling-project Makefiles, so they
require the source trees under `SOURCE_BASE` to be present. CI or a
fresh checkout without the sibling trees will skip these tests (see
test-fixture skip logic in the test files).

## 10. Out of scope

- The `deploy.sh` script at the repo root is a one-off blurb
  double-render fix recipe. It is not part of `deploytool` proper;
  keep it for historical reference but do not extend it.
- `bbsengine6` is a runtime dep of the deploy chain (`pyproject.toml`
  `dependencies`). deploytool does NOT orchestrate `bbsengine6`'s own
  install — that runs via `pip` when bbsengine6's wheel is installed
  by the per-project `deploy-tui` targets.
