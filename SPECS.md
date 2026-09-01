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
| `--dry-run` | Pass `--dry-run` through to each `make` invocation (appended to the cmd vector after the target) and export `DEPLOY_DRY_RUN=1` in the subprocess env. The per-project Makefile's `make -n` output is captured and printed. `make -n` failures still raise `DeployFailed(rc, label)`. The verify step (`run_verify`) does NOT invoke `php` under `--dry-run` since `php` has no dry-run flag. |
| `--timeout SECONDS` | Per-step subprocess timeout in seconds (default: `600`); expired timeouts abort the deploy with `DeployFailed(rc=-1)` |
| `--verify` | Run post-deploy verification step after the deploy chain |
| `--debug` | Debug mode |
| `--editable` | Install per-project Python packages in editable mode (`pip install -e`). Sets `DEPLOY_EDITABLE=1` in the `make` invocation's environment so each per-project Makefile can swap wheel install for editable install. See §2.1. |
| `--with-deps` | Include transitive dependencies in the chain. Default `false` — only caller-named projects run (no transitive dep walking). `--with-deps` does NOT auto-expand bare-base invocation; bare-base is ambiguous whenever `len(TARGETS[foo]) > 1` regardless of this flag. See §2.2. |
| `--upgrade` / `--no-upgrade` | Pass `--upgrade` to every `pip install` in the deploy chain. Default: enabled (the `deploy` command is opt-out, unlike the rest of the flags). Sets `DEPLOY_UPGRADE=1` in the `make` env when enabled; per-project Makefiles splice `--upgrade` into their `pip install` lines. Pass `--no-upgrade` for a hermetic deploy against the wheels in `$(OUTDIR)` only. See §2.3. |

Bare-base invocation rules (see §4 Sub-targets for detail):

- `deploy foo.tui` — pin explicit subs; no transitive deps unless
  `--with-deps` is also set.
- `deploy foo` (bare) — ambiguous when `TARGETS[foo]` has more than
  one entry. Exits `1` listing the subs, regardless of `--with-deps`.
  Caller must name a sub (e.g. `deploy foo.tui`).
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

### 2.1.1 `--dry-run` env-var contract

`--dry-run` follows the same single-source-of-truth pattern as
`--editable`. `lib.run_make_deploy` (`lib.py:428-469`) either sets
`DEPLOY_DRY_RUN=1` in the subprocess env (when `--dry-run` is
passed) or strips `DEPLOY_DRY_RUN` from the copied env (when it
isn't). Per-project Makefiles that want to opt into extra dry-run
behavior (e.g. skipping a side-effect that `make -n` alone won't
suppress, such as touching a stamp file in a `$(shell ...)` call)
can read `DEPLOY_DRY_RUN` directly. There are no legacy aliases
for this var.

Unlike `--editable`, `--dry-run` ALSO appends `--dry-run` to the
cmd vector so `make -n` is actually invoked — deploytool is not
short-circuiting the subprocess anymore. The operator sees the
per-project Makefile's recipe lines (e.g. the `pip install
/srv/repo/<project>/<project>-*.whl` line under default mode, or
the `cd py && pip install -e .` line under `--editable`).

The verify step (`run_verify`) does NOT honor `--dry-run` for the
underlying subprocess. `php test_blurb_render.php` has no dry-run
flag, so `run_verify` keeps its short-circuit: under `--dry-run`
the step is logged and skipped without invoking `php`.

### 2.2 `--with-deps` semantics

`--with-deps` controls a single behavior: whether transitive
dependencies are walked for each explicitly-named project. It does
NOT control sub-target expansion.

**Without `--with-deps` (default):**

- The dep walker (`lib.resolve` `visit()` at `lib.py:310-348`) skips
  both `DEPENDENCIES` and `CONDITIONAL_DEPENDENCIES`. Only the
  caller-named projects run.

**With `--with-deps`:**

- The dep walker pulls in every transitive dependency declared in
  `DEPENDENCIES` and the conditional-deps matching each requested
  sub.

**Bare-base invocation (independent of `--with-deps`):**

- Bare-base (`deploy foo` with no `.sub`) is **ambiguous** whenever
  `TARGETS[foo]` has more than one entry: the resolver prints the
  available subs and calls `sys.exit(1)`. The caller must name a
  sub (`deploy foo.tui`). `--with-deps` does not change this; the
  flag does not auto-expand bare-base. To deploy every sub of a
  base, name them explicitly:
  `deploy --with-deps casino.tui casino.www`.
- Projects with a single entry in `TARGETS` (e.g. `getdate_next ->
  ["tui"]`) auto-pick that one sub on bare invocation — no
  ambiguity possible.
- Projects with no `TARGETS` entry (e.g. `mistermcfeely`,
  `asimov`, `letteredolive`) run the bare `make deploy` target
  unconditionally on bare invocation.

`--with-deps` is orthogonal to `--editable`. `deploy --with-deps
--editable foo.tui` walks the chain and installs every package
editable. `--with-deps` IS plumbed to per-project Makefiles as
`DEPLOY_WITH_DEPS=1` so Makefiles that want to opt into less-strict
precondition behavior under an explicit "rebuild everything"
invocation can read it. See §2.2.1 for the env-var contract.

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

### 2.2.1 `DEPLOY_WITH_DEPS` env-var contract

`--with-deps` follows the same single-source-of-truth pattern as
`--editable` (see §2.1) and `--dry-run` (see §2.1.1).
`lib.run_make_deploy` (`lib.py:454-471`) either sets
`DEPLOY_WITH_DEPS=1` in the subprocess env (when `--with-deps` is
passed) or strips `DEPLOY_WITH_DEPS` from the copied env (when it
isn't). Per-project Makefiles that want to opt into less-strict
precondition behavior under an explicit "rebuild everything"
invocation can read `DEPLOY_WITH_DEPS` directly.

Current consumer: `bbsengine6/py/src/Makefile precheck-editable`.
With `DEPLOY_WITH_DEPS` empty (the default), the precheck
hard-fails if the active venv has an editable install of
`bbsengine6`. With `DEPLOY_WITH_DEPS=1`, the precheck warns and
proceeds; the post-install `verify-install` macro (same file) then
becomes the actual correctness check — the editable `.pth` finder
shadows the wheel install, `pip show` disagrees with the wheel's
METADATA, and the deploy aborts with a precise diagnosis. Projects
that don't read `DEPLOY_WITH_DEPS` are unaffected by either branch.

Unlike `--editable`, `--with-deps` does NOT need to plumb aliases
(EDITABLE, DEV) — there are no legacy names. There is no
deploytool-controlled "lock" mode for `DEPLOY_WITH_DEPS`; if the
operator wants the precheck to hard-fail under all conditions, they
omit `--with-deps` (or strip the env var themselves).

#### 2.2.1.1 Editable-shadow contract (PEP 660)

The reason the `DEPLOY_WITH_DEPS` env var exists at all is the
PEP 660 editable-installer shadow: when an editable install of
`bbsengine6` already lives in the active venv, `pip install
<wheel>` writes a fresh `dist-info/` but the editable's
`__editable___bbsengine6_*_finder` `.pth` hook wins on `import`,
so the operator's TUI keeps loading source-tree code while
`pip show` reports the freshly-installed wheel version. There is
no in-place fix — editable and wheel installs of the same
distribution name cannot coexist in one venv.

Under `DEPLOY_WITH_DEPS` unset (the default), the
`bbsengine6/py/src/Makefile precheck-editable` recipe bails
non-zero before the install even runs, with a breadcrumb naming
the editable source path and the two clean remedies
(`deploy --editable bbsengine6.tui` to stay editable;
`pip uninstall bbsengine6 && deploy bbsengine6.tui` to switch to
wheels). Under `DEPLOY_WITH_DEPS=1`, the precheck warns and
proceeds; the post-install `verify-install` macro
(`Makefile:69-91`) then becomes the actual correctness contract —
the editable `.pth` finder shadows the wheel install, `pip show`
disagrees with the wheel's METADATA, and the deploy aborts with a
precise diagnosis naming the editable-install cause. End-to-end
pinning of both contracts lives in
`tests/test_deploy_shadow_install.py`.

### 2.3 `--upgrade` / `--no-upgrade` semantics

`--upgrade` is the **only** CLI flag in deploytool whose default is
*enabled* — the other flags (`--editable`, `--with-deps`,
`--dry-run`, `--verify`) are all opt-in. Rationale: the deploy
chain is the standard way to bring a venv up to the freshly-built
wheel, and operators expect transitive deps to track their PyPI
releases between deploys (otherwise stale `requests`, `urllib3`,
etc. accumulate across deploys and become a security liability).
Operators who need a hermetic deploy against the wheels in
`$(OUTDIR)` only (e.g. for a CI smoke test or an offline prod
deploy) pass `--no-upgrade`.

**Default (no flag):**

- `lib.run_make_deploy` sets `DEPLOY_UPGRADE=1` in the subprocess
  env. Every per-project Makefile splices `--upgrade` into its
  `pip install` lines so the install replaces any prior version of
  the same distribution and pulls the newest transitive deps from
  PyPI.

**With `--no-upgrade`:**

- `lib.run_make_deploy` strips `DEPLOY_UPGRADE` from the copied
  env (mirroring the `DEPLOY_EDITABLE` / `DEPLOY_WITH_DEPS` /
  `DEPLOY_DRY_RUN` strip-on-inherit pattern). Per-project
  Makefiles fall through to the prior no-op-if-version-matches
  behavior: `pip install <wheel>` is a no-op when the wheel
  version already matches what's installed, and transitive deps
  stay whatever they were in the target venv at deploy time.

**Env-var contract (`DEPLOY_UPGRADE`):**

The literal-string comparison `ifeq ($(DEPLOY_UPGRADE),1)` is the
gate per project Makefiles use to decide whether to splice
`--upgrade`. deploytool is the canonical writer: it sets to `1`
when `--upgrade` is in effect (the default), strips entirely
when `--no-upgrade` is passed. The literal-string match is
intentional — `ifeq` is exact-match, so any operator-shell
artifact like `DEPLOY_UPGRADE=true` or `DEPLOY_UPGRADE=on` falls
through to the no-upgrade branch. Operators should set this only
via the `--upgrade` / `--no-upgrade` CLI flags; setting it
directly in the shell is unsupported.

There are no legacy aliases for `DEPLOY_UPGRADE` (no `UPGRADE`
or `UPGRADE_PIP` to mirror the `EDITABLE` / `DEV` legacy names).
The only consumer of `DEPLOY_UPGRADE` is each per-project
Makefile's `pip install` invocation. The `pip install --upgrade
pip` line in each `install-venv` block is intentionally NOT
gated on `DEPLOY_UPGRADE` — a stale `pip` breaks everything
downstream and is unrelated to the project wheel install.

#### 2.3.1 Per-project Makefile wiring

Every per-project Makefile in the deploy chain declares
`DEPLOY_UPGRADE ?=` and a derived `PIP_UPGRADE_FLAG`:

```make
DEPLOY_UPGRADE ?=
PIP_UPGRADE_FLAG := $(if $(filter 1,$(DEPLOY_UPGRADE)),--upgrade,)
```

`PIP_UPGRADE_FLAG` is then spliced into every `pip install` line
in the Makefile — yielding e.g.
`$(PIP) install $(PIP_UPGRADE_FLAG) --no-cache-dir $$WHEEL`
in `bbsengine6/py/src/Makefile:deploy-tui`. When
`DEPLOY_UPGRADE` is unset (empty), the variable expands to the
empty string, and the recipe line is byte-identical to the
pre-`--upgrade` form. Per-project files wired up:

- `deploytool/Makefile`
- `bbsengine6/Makefile` (top-level; also forwards
  `DEPLOY_UPGRADE=$(DEPLOY_UPGRADE)` to the `py/src` sub-make at
  the `deploy-tui` target)
- `bbsengine6/py/src/Makefile`
- `bed/Makefile`
- `casino/Makefile`
- `zoid6/src/Makefile` (covers `install`, `install-dev`,
  `egg-info`, `deploy-tui`, `install-venv`, and `install-user`)
- `zoidoffice/src/Makefile`
- `getdate_next/Makefile`
- `yummyjam/article2/Makefile` (covers `install` and
  `install-dev`)
- `mistermcfeely/Makefile`

Regression coverage: `tests/test_deploy_upgrade.py` asserts
each of those files declares `DEPLOY_UPGRADE ?=` and defines
`PIP_UPGRADE_FLAG := ...`, and that the `pip install` lines
contain the `$(PIP_UPGRADE_FLAG)` splice.

### 3.1 Sub-target dedup

A single `deploy` call that requests the same base with multiple subs
expands each sub into its own walker seed. Two subs that alias to the
same `deploy-*` make target (see §5) collapse to one `make` invocation
in the final order.

### 3.2 `prod` opt-in

`prod` is a sudo-umbrella install for `bed`, `zoid6`, and
`mistermcfeely` and must not run by default. The drop gate
(`lib.py:362`) keeps `prod` out of the final order unless the
caller named it explicitly (`deploy bed.prod`,
`deploy mistermcfeely.prod`) or a transitive explicit dep
named it. Bare-base invocation never pulls in `prod` because it
never auto-expands (§2.2) — callers must name `prod` to opt in.

For `mistermcfeely` specifically, the `prod` sub-target is the
only one that uses `sudo`. The `tui` sub-target is operator-side
(no sudo) — it builds wheels into `/srv/repo/mistermcfeely/` and
installs into the operator's active venv. The split exists so
the cross-project PEP 660 editable-shadow precheck and
verify-install macros can run from operator context without
needing `sudo` to query the target venv's dist-info. See §5.1
for the tui/prod shape contract.

## 4. Sub-targets

Encoded in `lib.py:121-134` (`TARGETS`). A bare sub is `[None]`,
meaning "no `deploy-<sub>` suffix; run the project's bare `deploy`
target." Project records in `TARGETS` look like:

```
"casino":        ["tui", "www"],
"bed":           ["tui", "venv", "prod"],
"getdate_next":  ["tui"],
"mistermcfeely": ["tui", "prod"],
```

Bare-base invocation semantics (see `lib.resolve` lines
`lib.py:217-308`):

- `deploy proj.tui` (or any explicit sub) — pins that sub. No
  transitive deps unless `--with-deps` is set (see §2.2).
- `deploy proj` (bare) — ambiguous when `len(TARGETS[proj]) > 1`.
  The resolver prints the available subs and exits `1`, regardless
  of `--with-deps`. Caller must name a sub explicitly.
- `deploy proj` (bare, single-sub `TARGETS`) — auto-picks that
  one sub. No ambiguity to begin with (e.g. `deploy getdate_next`
  → `getdate_next.tui`).
- `deploy proj` (bare, no `TARGETS[proj]` entry) — runs the bare
  `make deploy` target; nothing to choose.

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

### 5.1 `tui` / `prod` split (mistermcfeely)

`mistermcfeely` is the only project whose `tui` sub-target
installs into the **shared zoid6 venv** (`/var/lib/zoid6/venv`)
rather than the operator's active venv. The split into `tui`
(operator-side, no sudo) and `prod` (sudo umbrella) exists so
the PEP 660 editable-shadow precheck and verify-install macros
can run from operator context without `sudo`.

**`deploy mistermcfeely.tui`** (no sudo, no `sudo -u zoid6`):

1. Builds `bbsengine6` + `mistermcfeely` wheels into
   `/srv/repo/mistermcfeely/` (the canonical cross-project
   `OUTDIR`, matching `bed/OUTDIR=/srv/repo/bed/` and
   `casino/OUTDIR=/srv/repo/casino/`).
2. Runs `precheck-editable` against the operator's active venv
   (reads `dist-info/direct_url.json` directly; no `pip show`,
   no `sudo`).
3. Either installs editable from source (`DEPLOY_EDITABLE=1`,
   set by `deploytool --editable`) or installs the freshly-built
   wheel into the operator's active venv.
4. Runs `verify-install` against the operator's active venv
   (reads `dist-info/METADATA` directly; no `pip show`,
   no `sudo`).

**`deploy mistermcfeely.prod`** (sudo umbrella):

1. Runs `install-sysusers` (`sudo rsync` + `sudo systemd-sysusers`).
2. Runs `install-tmpfiles` (`sudo rsync` + `sudo systemd-tmpfiles`).
3. Runs `install-venv` (the only target with shared-venv
   install logic):
   - Creates the venv at `/var/lib/zoid6/venv` via
     `sudo -u zoid6 ...` if missing.
   - Upgrades pip and installs `build setuptools wheel` into
     the shared venv via `sudo -u zoid6 $(VENV_DIR)/bin/pip ...`.
   - Runs `precheck-editable` as the operator (no sudo) using
     `$(VENV_DIR)/bin/python` to resolve site-packages for the
     shared venv — direct `dist-info/direct_url.json` reads.
   - Re-runs `make build` so the wheels in `/srv/repo/...`
     reflect the current source (the operator doesn't have to
     call `deploy-tui` first).
   - Installs `$(OUTDIR)/*.whl` into the shared venv via
     `sudo -u zoid6 $(VENV_DIR)/bin/pip install ...`.
   - Runs `verify-install` as the operator (no sudo) using
     `$(VENV_DIR)/bin/python` — direct `dist-info/METADATA` reads.
4. Runs `install-systemd` (`sudo tee` + `sudo systemctl daemon-reload`).
5. Runs `install-etc` (multiple `sudo rsync` invocations for
   `mcfeely-authd.conf`, `saslauthd.*`, `pam.d-saslauthd`).

**Why precheck + verify don't use `sudo`:** they read the
target venv's `dist-info/` directly via `sysconfig.get_paths()["purelib"]`
run by the venv's own `python` interpreter. The interpreter is
invoked by the operator shell (no sudo); `site-packages/` and
`dist-info/` are world-readable in a normal pip install; the
macros SKIP with a message if they're not (rather than failing
with permission-denied).

The two macros (`precheck-editable`, `verify-install`) iterate
over `WHEEL_PACKAGES := bbsengine6 mistermcfeely` so a single
macro call covers the batch install. Adding a new package whose
wheel is also installed by `install-venv` is a one-line change
to that variable.

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
- `test_deploy_upgrade.py` — `--upgrade` / `--no-upgrade` flag,
  `DEPLOY_UPGRADE` env-var plumbing (set when flag is passed /
  default-on, stripped when `--no-upgrade` is passed, strips a
  pre-existing shell var), and Makefile-presence assertions that
  each per-project Makefile in §2.3.1 declares `DEPLOY_UPGRADE ?=`
  and splices `$(PIP_UPGRADE_FLAG)` into its `pip install` lines.

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
