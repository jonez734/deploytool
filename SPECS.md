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
| `--timeout SECONDS` | Per-step subprocess timeout in seconds (default: `600`); expired timeouts abort the deploy with `DeployFailed(rc=-1)` |
| `--verify` | Run post-deploy verification step after the deploy chain |
| `--debug` | Debug mode |
| `--editable` | Install per-project Python packages in editable mode (`pip install -e`). Sets `DEPLOY_EDITABLE=1` in the `make` invocation's environment so each per-project Makefile can swap wheel install for editable install. See §2.1. |
| `--with-deps` | Include transitive dependencies in the chain. Default `false` — only caller-named projects run (no transitive dep walking). Bare-base invocation (`deploy foo` with no `.sub`) under `--with-deps` also auto-expands to every entry in `TARGETS[foo]`. Bare-base invocation without `--with-deps` is ambiguous when `len(TARGETS[foo]) > 1`: the resolver lists the subs and exits `1`. See §2.2. |

Bare-base invocation rules (see §4 Sub-targets for detail):

- `deploy foo.tui` — pin explicit subs; no transitive deps unless
  `--with-deps` is also set.
- `deploy foo` (bare) — ambiguous when `TARGETS[foo]` has more than
  one entry. Exits `1` listing the subs. Pass `--with-deps` to
  auto-expand instead (see §2.2).
- `deploy foo` (bare, `TARGETS[foo]` is empty) — runs the bare
  `make deploy` target; no ambiguity possible.

### 2.1 `--editable` semantics

`--editable` flips the install mode across every `deploy-tui`-style
target in the chain:

- **Default (no `--editable`)**: each project's `deploy-tui`
  target installs the most-recently-built wheel from
  `/srv/repo/<project>/<project>-*.whl` into the active venv
  (or `/var/lib/<project>/venv` for projects with a per-service
  venv). The wheel filename embeds the version from
  `pyproject.toml`'s `[tool.setuptools.dynamic] version = ...`
  attribute, so the glob omits the version stamp. Recipes pick
  the newest entry with `ls -t | head -1`.
- **`--editable` set**: each project's `deploy-tui` target
  installs editable from the source tree (`pip install -e ...`).
  Source-tree edits are picked up by the next interpreter start
  without a rebuild + reinstall. Independent of `OUTDIR` — the
  editable install path is the source tree, not `/srv/repo/`.

Mechanism: `lib.py:428-470` (`run_make_deploy`) sets
`DEPLOY_EDITABLE=1` in the subprocess env when `--editable` is
passed. When `--editable` is **not** passed, deploytool is the
sole source of truth: it copies `os.environ` and then explicitly
**strips** `DEPLOY_EDITABLE`, `EDITABLE`, and `DEV` from the
copied dict, so an operator who happens to have one of those vars
set in their shell does not accidentally trigger editable mode.
Per-project Makefiles should treat any of these env vars as
untrusted when deploytool is the caller.

Why strip `EDITABLE` and `DEV` even though they are bed-only
legacy names: bed's Makefile accepts all three (canonical
`EDITABLE`, deploytool's `DEPLOY_EDITABLE`, and the legacy
`DEV=1`). If deploytool only stripped `DEPLOY_EDITABLE`, a stray
`EDITABLE=1` or `DEV=1` in the operator's shell could still
trigger bed's editable path without `--editable`. The three-way
strip closes that gap.

### 2.2 `--with-deps` semantics

`--with-deps` controls two orthogonal behaviors at once: whether
transitive dependencies are walked, and whether bare-base invocation
auto-expands to all subs.

**Without `--with-deps` (default):**

- The dep walker (`lib.resolve` `visit()` at `lib.py:310-348`) skips
  both `DEPENDENCIES` and `CONDITIONAL_DEPENDENCIES`. Only the
  caller-named projects run.
- Bare-base invocation (`deploy foo` with no `.sub`) is **ambiguous**
  when `TARGETS[foo]` has more than one entry: the resolver prints
  the available subs and calls `sys.exit(1)`. The caller must name a
  sub (`deploy foo.tui`) or pass `--with-deps`.
- Projects with a single entry in `TARGETS` (e.g. `getdate_next ->
  ["tui"]`) auto-pick that one sub on bare invocation — no
  ambiguity possible.
- Projects with no `TARGETS` entry (e.g. `mistermcfeely`,
  `asimov`, `letteredolive`) run the bare `make deploy` target
  unconditionally on bare invocation.

**With `--with-deps`:**

- The dep walker pulls in every transitive dependency declared in
  `DEPENDENCIES` and the conditional-deps matching each requested
  sub.
- Bare-base invocation auto-expands to every entry in `TARGETS[foo]`
  — the "build the whole thing" shortcut. `deploy --with-deps casino`
  runs both `casino.tui` and `casino.www` and walks their full dep
  chains (`bbsengine6.{tui, www}`, `bed.tui`, etc.).
- The auto-expansion populates `explicit_subs` for every subs in
  `TARGETS[foo]`. This interacts with the `prod` opt-in drop
  (§3.2): auto-expanded `prod` subs survive the drop because the
  drop gate (`lib.py:362`) only skips entries NOT in
  `explicit_subs`.

`--with-deps` is orthogonal to `--editable`. `deploy --with-deps
--editable foo.tui` walks the chain and installs every package
editable. `--with-deps` does NOT plumb a `DEPLOY_WITH_DEPS=1` env
var into `make` invocations — the flag is purely a deploytool-side
resolver concern; per-project Makefiles don't need to know.

## 3. Dependency graph

Encoded in `lib.py:36-54` (`DEPENDENCIES`) and
`lib.py:100-119` (`CONDITIONAL_DEPENDENCIES`). Rules:

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
run by default. `lib.py:362` drops auto-expanded `prod` entries
from the final order; only `prod` subs the caller (or a transitive
explicit dep, or `--with-deps` auto-expansion at `lib.py:266-271`)
named explicitly survive.

## 4. Sub-targets

Encoded in `lib.py:121-133` (`TARGETS`). A bare sub is `[None]`,
meaning "no `deploy-<sub>` suffix; run the project's bare `deploy`
target." Project records in `TARGETS` look like:

```
"casino": ["tui", "www"],
"bed":    ["tui", "venv", "prod"],
"getdate_next": ["tui"],
```

Bare-base invocation semantics (see `lib.resolve` lines
`lib.py:217-308`):

- `deploy proj.tui` (or any explicit sub) — pins that sub. No
  transitive deps unless `--with-deps` is set (see §2.2).
- `deploy proj` (bare, no `--with-deps`) — ambiguous when
  `len(TARGETS[proj]) > 1`. The resolver prints the available
  subs and exits `1`. Caller must name a sub or pass `--with-deps`.
- `deploy proj` (bare, single-sub `TARGETS`) — auto-picks that
  one sub. No ambiguity to begin with (e.g. `deploy getdate_next`
  → `getdate_next.tui`).
- `deploy proj` (bare, no `TARGETS[proj]` entry) — runs the bare
  `make deploy` target; nothing to choose.
- `deploy --with-deps proj` (bare, `--with-deps` set) — auto-
  expands to every entry in `TARGETS[proj]` AND walks the full
  transitive dep chain.

Sub names are user-facing. The actual `make` target name may differ —
see §5.

## 5. Make target aliases

Encoded in `lib.py:138-141` (`MAKE_TARGET_ALIASES`). Maps a
`(project, sub)` pair to the `deploy-<sub>` make target name to run
when the user requested that sub. Applied by `run_make_deploy`
(`lib.py:428-470`) before constructing the cmd vector. Currently:

- `("bed", "tui")` → `"venv"` — `bed` has no `deploy-tui` target;
  its `tui` is a Python venv install.
- `("getdate_next", "tui")` → `"venv"` — same reason.

Bare projects (sub is `None`) get `deploy` as the make target.

## 6. Aliases

Encoded in `lib.py:56-58` (`ALIASES`) and `lib.py:60-62`
(`ALIAS_PATTERNS`). A user-facing project name that should be
canonicalized before any other processing. Pattern-based aliases
apply first; literal aliases second.

## 7. Venv registry

Encoded in `lib.py:65-85` (`VENV_USER`, `VENV_LAYOUT`).
`get_venv_layout` (`lib.py:148-162`) resolves a project's venv:

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

`PROJECT_DIRS` (`lib.py:32-34`) lists projects whose source tree
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

## 11. Abort behavior

Both `lib.run_make_deploy` and `lib.run_verify` abort the deploy by
raising `deploytool.lib.DeployFailed(rc, label)` on:

- non-zero subprocess returncode (`rc` = the subprocess rc);
- `subprocess.TimeoutExpired` (`rc = -1`; timeout is `args.timeout`,
  default `DEFAULT_TIMEOUT_SECONDS` = 600s — overridable via
  `--timeout`);
- `FileNotFoundError` (`rc = -1`; e.g. `make` or `php` not installed);
- `OSError` (`rc = -1`).

`KeyboardInterrupt` and other `BaseException`s are NOT caught — the
user can Ctrl-C and the deploy halts cleanly.

Both functions run subprocesses with explicit `encoding="utf-8"`,
`errors="replace"`, `timeout=args.timeout`, `check=False`, and
`start_new_session=True` so:

- non-UTF8 subprocess output cannot crash the parent with
  `UnicodeDecodeError`;
- hung steps do not block the chain forever;
- the child has its own process group, which makes cleanup on signal
  more reliable.

`main.main()` catches `DeployFailed` once per call site (once around
the make loop, once around the verify step) and returns 1 with a
single, structured abort message that includes the failing step's
`label` and `rc`. The chain stops at the failing project; a failed
verify step no longer reports `deploy complete`.
