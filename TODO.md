# deploytool — TODO

## Repo status (2026-08-20)

This repo is **standalone** as of 2026-08-20. It is no longer tracked
as part of the parent monorepo at `/home/opencode/data/work/`; that
tree now lists `deploytool/` in its `.gitignore`. Standalone-repo
launch event:

- `origin` → `git@github.com:jonez734/deploytool.git`
- Commit log on `main`: `2a96859` initial scaffolding →
  `9120024` SPECS → `1495025` README → `c3752b0` CHANGELOG →
  (this TODO update) → (`make test` target) → (regenerated
  `_version.py`). See [CHANGELOG.md](CHANGELOG.md).
- Project still lives **on disk** under
  `/home/opencode/data/work/deploytool/`, because the per-project
  `Makefile`s it orchestrates expect it there via the
  `SOURCE_BASE` convention documented in `SPECS.md §6`. The
  standalone `.git/` is local to that path; the parent's tree
  ignores it.

Sister projects under `/home/opencode/data/work/` (e.g. `bed/`,
`bbsengine6/`, `casino/`) are siblings of `deploytool/` in the
same monorepo on disk; they each have their own publish workflow
and are not in scope for this repo's docs beyond what `lib.py`
references.

[x] Default sub-target semantics. Resolved 2026-08-20: `deploy <project>`
    with no sub no longer picks `targets[0]` — it runs every sub in
    `TARGETS`. `TARGETS` at `src/deploytool/lib.py:96-106` is
    now an ordered list of subs to deploy, not a default-and-alternates
    registry. Caller can still pin a single sub (`deploy foo.tui`) to
    restrict.

    ```
    "zoid6":       ["www", "tui", "prod"]  # prod opt-in (sudo umbrella, alias for install-fhs)
    "teos":        ["www", "tui"]
    "achilles":    ["www", "tui"]
    "casino":      ["tui", "www"]
    "article2":    ["www", "tui"]
    "backuptools": ["www", "tui"]
    "deploytool":  ["tui"]
    "zoidoffice":  ["tui"]
    "bed":         ["tui", "venv", "prod"]  # tui aliased to venv; prod opt-in
    "bbsengine6":  ["tui", "www"]   # new entry; was implicit www via bare deploy
    ```

    **Exception:** `prod` is opt-in — auto-expanded `prod` is dropped from
    the deploy at `src/deploytool/lib.py:296` unless the user
    (or a transitive explicit dep) named it. `prod` is the sudo umbrella
    install for bed (`bed/Makefile:220-221`) and zoid6 (`zoid6/src/Makefile`
    `deploy-prod: install-fhs`) and shouldn't run by default. `deploy
    bed` runs `tui`+`venv`; `deploy bed.prod` runs just `prod`;
    `deploy bed.tui bed.prod` runs both. Same for `deploy zoid6` (auto-
    drops `prod`) vs `deploy zoid6.prod` (explicit).

    Audit each project's Makefile (especially www-only ones like
    `teos/Makefile:29` and `murdermotel/Makefile:35`) for what its
    `deploy-tui` target actually does — the new semantics mean
    `deploy teos` now triggers a wheel install the caller didn't expect.

[x] `resolve()` collapsed multiple sub-targets of the same project to the
    last one in a single deploy call. Resolved 2026-08-20 by changing
    `project_info` from `dict[str, str]` to `dict[str, list[str]]` in
    `src/deploytool/lib.py:176-263` and rebuilding the topo
    sort to seed one `visit()` call per requested sub. Plus a second
    dedup pass after `MAKE_TARGET_ALIASES` resolution so `bed.tui` and
    `bed.venv` (which both resolve to `deploy-venv`) don't double-run.
    Verify by re-running `deploy --dry-run article2.tui article2.www`
    and expecting `bbsengine6.tui, bbsengine6.www, article2.tui,
    article2.www`.

[ ] `VENV_LAYOUT` at `src/deploytool/lib.py:55-70` hardcodes
    `/var/lib/zoid6/venv` for six packages whose Makefiles do NOT
    actually install there. The registry is documentation-only (per
    `lib.py:53-54`: "Registry only: deploytool does not plumb venv
    vars into `make`; per-project Makefile defaults and `pip` handle
    venv targeting"), so the hardcoded value misleads anyone reading
    the registry about where these packages land on a `deploy` call.

    Change these six entries from `"/var/lib/zoid6/venv"` to the
    `VENV_USER` sentinel already used by `backuptools` and
    `deploytool` at `lib.py:68-69`:

      - `"casino"`        — `casino/Makefile:104` `deploy-tui: install`
                            runs `pip install -e .` against the active
                            venv. Casino has no `VENV_DIR`.
      - `"teos"`          — `teos/Makefile:29` `deploy: deploy-www` is
                            www-only (blurbs + rsync). No Python install.
      - `"murdermotel"`   — `murdermotel/Makefile:35` `deploy: www` is
                            www-only.
      - `"empyre"`        — `empyre/Makefile:29` `deploy: version` is
                            a version bump. No install path.
      - `"letteredolive"` — `letteredolive/Makefile:38` `deploy: build`
                            is a build step. No install path.
      - `"zoidoffice"`    — `zoidoffice/Makefile:34`
                            `deploy-tui: build` runs
                            `$(MAKE) -C src install`, which is
                            `pip install -e .` against the active venv.

    Leave as-is (each has a real reason to target
    `/var/lib/zoid6/venv`):

      - `"zoid6"` — matches zoid6's own deploy conventions.

    Note: `"mistermcfeely"` previously sat in this group too because
    `mistermcfeely/Makefile:73` set `VENV_DIR ?= /var/lib/zoid6/venv`.
    That decision is reversed — `mistermcfeely` is moving to a
    per-service venv (`/var/lib/mistermcfeely/venv`) matching `bed`,
    tracked under "Deploy targets and venv layout (per-service, like
    bed)" in `mistermcfeely/TODO.md`. Once that lands, the deploytool
    `VENV_LAYOUT` entry for `mistermcfeely` should change from
    `"/var/lib/zoid6/venv"` to `"/var/lib/mistermcfeely/venv"` to
    match the new Makefile default.

    Verification: `git diff src/deploytool/lib.py` shows
    six `"/var/lib/zoid6/venv"` → `VENV_USER` substitutions plus the
    sentinel comment at `lib.py:49-50`, nothing else.

[ ] `VENV_LAYOUT` cannot express sub-target variation, so the
    `bbsengine6` and `achilles` entries are wrong on the sub-targets
    that don't install Python:

      - `bbsengine6.tui` — `bbsengine6/Makefile:172`
        `deploy-tui: $(MAKE) -C py/src install` runs `pip install -e
        .` against the active venv (active at deploy time). Should
        resolve like the six above (VENV_USER).
      - `bbsengine6.www` — `bbsengine6/Makefile:160`
        `deploy-www: deploy` is rsync of www files, no Python install
        at all. Should not appear in VENV_LAYOUT.
      - `achilles.www` — `achilles/Makefile:59` `deploy: www` is
        www-only. Same.
      - `achilles.tui` — `achilles/Makefile` defines no `deploy-tui`
        target as of this writing; verify before assuming.

    The current entry `"bbsengine6": "/var/lib/zoid6/venv"` is
    accidentally right only because `bbsengine6` is pulled in as a
    transitive dep of `zoid6.tui` (per `CONDITIONAL_DEPENDENCIES` at
    `lib.py:74-78`), where the active venv IS `/var/lib/zoid6/venv`.
    Standalone `deploy bbsengine6.tui` would target whatever venv is
    active at deploy time — different behavior than the registry
    claims.

    Fix options (pick one):

      (a) Remove `"bbsengine6"` and `"achilles"` from `VENV_LAYOUT`
          entirely; let them default to `VENV_USER`. Simplest.
      (b) Extend the registry to be sub-target aware, e.g.
          `VENV_LAYOUT["bbsengine6"] = {"tui": VENV_USER, "www":
          None}`. Requires changing the type of `VENV_LAYOUT` and
          updating `get_venv_layout` at `lib.py:112-126` to consult
          the requested sub.

    Default to option (a) unless a future ticket needs (b).

    Verification: `deploytool --dry-run bbsengine6.tui` and
    `deploytool --dry-run bbsengine6.www` both produce the right
    `make` invocations from `bbsengine6/Makefile`, and the registry
    no longer claims `bbsengine6` lives in `/var/lib/zoid6/venv`.

[ ] The docstring at `src/deploytool/lib.py:49-54`
    explains `VENV_USER` and `VENV_LAYOUT` but does not warn the
    reader that the registry values are claims about where each
    project installs, which may not match the per-project Makefile
    reality (see the two preceding TODO entries for six stale
    entries and two sub-target-aware entries).

    Tighten the comment so a future maintainer reading `VENV_LAYOUT`
    understands:

      1. Each value is a CLAIM about the per-project Makefile's
         default `VENV_DIR` / `pip` target, not a deployment
         instruction. The registry is informational.
      2. `VENV_USER` means "no claim — defer to the active venv at
         deploy time." Use it for any project whose Makefile has no
         `VENV_DIR` and runs `pip install -e .` against `$VIRTUAL_ENV`
         / `$(PYTHON)`.
      3. If a project's Makefile defines multiple sub-targets with
         different install paths (see bbsengine6 above), prefer
         `VENV_USER` and document the sub-target split in that
         project's Makefile comment rather than encoding it in the
         registry.

    Suggested replacement text (replace `lib.py:49-54`):

    ```
    # Sentinel: "the user's active venv", resolved at runtime by
    # get_venv_layout(). Use this for any project whose Makefile
    # runs `pip install` against $(PYTHON) without an explicit
    # VENV_DIR.
    VENV_USER = None

    # Venv registry (project -> venv path). Registry only: deploytool
    # does not plumb venv vars into `make`; per-project Makefile
    # defaults and `pip` handle venv targeting. Each entry should
    # reflect what the project's Makefile actually does on its deploy
    # target — do NOT hardcode `/var/lib/<x>/venv` for a project
    # unless you have verified its Makefile agrees. Projects not
    # listed default to VENV_USER.
    VENV_LAYOUT = { ... }
    ```

    Verification: re-read the diff for `lib.py:49-54` and confirm
    (a) the new wording is consistent with the refactor in the two
    preceding TODO entries, and (b) no other docstring in the file
    contradicts it.

# Phase 0: standardize wheel output to `/srv/repo/<project>/`

`make build` currently writes wheels to each project's local `dist/`
(or `../dist/` from subdirs). Standardize the output to
`/srv/repo/<project>/<project>-*.whl` so all three projects share one
predictable location, the dir is setgid-`repo` so newly-dropped wheels
inherit correct group ownership, and Phase 1's `deploy` can install
from a known path.

## Destination and mechanics

[ ] **Single canonical path**: `/srv/repo/<project>/` (per-project
    subdir under `/srv/repo/`). Top-level `OUTDIR = /srv/repo/$(PROJECT)/`
    in each project's top-level Makefile. Same var in sub-Makefiles.

[ ] **Build via `python -m build --outdir $(OUTDIR)`** — drops the
    wheel straight into `/srv/repo/<project>/`. No rsync step. Build
    runner is `jam` (only user in the `repo` group), so newly-dropped
    wheels are owned `repo:repo` from the start.

[ ] **`/srv/repo/` perms**: `chgrp repo /srv/repo; chmod 2775 /srv/repo`.
    Setgid + group write so any subdir created under it inherits the
    `repo` group, and any wheel dropped into a subdir inherits group
    ownership.

[ ] **`/srv/repo/<project>/` perms**: `chgrp repo; chmod 2775`. Same
    setgid inheritance.

## Idempotent helper targets

`make build` must safely fix perms on every run, not just the first,
because perms can drift (manual edits, accidental `chmod`, etc.).
Add helpers to each top-level Makefile:

[ ] **`ensure-repo`** — guard with
    `stat -c '%G' /srv/repo | grep -qx repo` and
    `stat -c '%a' /srv/repo | grep -q '^2775$'`. Only runs
    `sudo chgrp` / `sudo chmod` if those checks fail. No-op when
    perms already correct.

[ ] **`ensure-build-dir: ensure-repo`** — `mkdir -p
    /srv/repo/$(PROJECT)/` then same `stat | grep` guards on
    `/srv/repo/$(PROJECT)/`. Idempotent.

[ ] **`build: version ensure-build-dir`** — depends on
    `ensure-build-dir` so perms are guaranteed correct before the
    build runs.

## Per-Makefile changes (8 files)

[ ] **`bed/Makefile`** (top-level) — add `ensure-repo`,
    `ensure-build-dir`. Update `.PHONY`. `build` body becomes
    `$(MAKE) ensure-build-dir` then
    `$(PYTHON) -m build --outdir $(OUTDIR)`. Already has
    `OUTDIR = /srv/repo/$(PROJECT)/`.

[ ] **`bed/src/Makefile`** — remove sub-level `build` target
    (lines 27-28). Update `.PHONY`. Update `OUTDIR` from
    `../dist/ # /srv/repo/$(PROJECT)/` to `/srv/repo/$(PROJECT)/`.
    Drop the TODO at line 54. `release:` (line 46) becomes
    `release: ; $(MAKE) -C .. release`.

[ ] **`bbsengine6/Makefile`** (top-level) — add
    `OUTDIR = /srv/repo/$(PROJECT)/` (after `PROJECT` at line 5).
    Add `version`, `rename-sdist`, `sign`, `wheel-release`, plus
    the two `ensure-*` helpers and a `build` target. Update `.PHONY`.
    **Leave `release` tarball target (lines 62-79) and
    `PROJECTRELEASEDIR` (line 9) untouched.**

[ ] **`bbsengine6/py/Makefile`** — add `OUTDIR =
    /srv/repo/$(PROJECT)/` only (already no build target).

[ ] **`bbsengine6/py/src/Makefile`** — remove sub-level `build`
    target. Update `.PHONY`. Update `OUTDIR` to
    `/srv/repo/$(PROJECT)/`. `release:` (line 33) becomes
    `release: ; $(MAKE) -C ../.. wheel-release` (delegates to top
    because top-level `release` is the unrelated tarball target).

[ ] **`casino/Makefile`** (top-level) — add `OUTDIR =
    /srv/repo/$(PROJECT)/` (around line 23). Add `rename-sdist`,
    `sign`, `release` targets (parallels bed top-level). Add
    `ensure-repo`, `ensure-build-dir` helpers. `build` and `sdist`
    bodies use `$(OUTDIR)` and depend on `ensure-build-dir`. Update
    `.PHONY` and `help` text.

[ ] **`casino/src/Makefile`** — add `PROJECT = casino` and
    `OUTDIR = /srv/repo/$(PROJECT)/` declarations (currently has
    only `all:` and `clean:`). Future-proofs sub-Makefile.

[ ] **`casino/src/casino/Makefile`** — remove sub-level `build`
    target. Update `.PHONY`. Update `OUTDIR` from `dist` to
    `/srv/repo/$(PROJECT)/`. Drop TODO at line 72. `release:` (line
    54) becomes `release: ; $(MAKE) -C ../.. release`.

## Verification

[ ] **Dry-run** each project's `make build`: `make -n build` shows
    `$(MAKE) ensure-build-dir` then
    `$(PYTHON) -m build --outdir /srv/repo/$(PROJECT)/`.

[ ] **Real run as `jam`**: `sudo -u jam make build` in each
    project, then `ls -l /srv/repo/<project>/` shows new wheel
    owned `repo:repo`, mode `0664` (inherited from setgid).

[ ] **Perms check**: `stat -c '%a %U %G' /srv/repo/` returns
    `2775 root repo`. Same for `/srv/repo/<project>/`.

[ ] **Idempotency**: run `make build` twice in a row, second run
    should be a no-op for the helper targets (stat checks pass).

[ ] **Cleanup**: `rm -rf bed/dist/ bbsengine6/dist/ casino/dist/`
    (all gitignored). `git status` shows only Makefile changes.

## Out of scope (Phase 2, deferred)

[ ] **Phase 2**: introduce `/srv/repo/<project>/dist/` subdir so
    wheels live one level deeper. Separate future change.
[ ] **Migration of pre-existing wheels** under `/srv/repo/bed/` and
    `/srv/repo/bbsengine6/`: leave them where they are.
[ ] **`bbsengine6/Makefile:PROJECTRELEASEDIR`** and the existing
    `release` tarball target: untouched.

# Phase 1: `deploy` wheel-install + `--dev` flag

Phase 1 flips three per-project Makefiles to install the wheel that
`make build` produces (which after Phase 0 lands in
`/srv/repo/<project>/<project>-<VERSION>-*.whl`), and adds a `--dev`
flag so the install mode can be toggled between wheel and editable.
**Phase 0 must land first** — these install paths depend on it.

## Install pattern: explicit single wheel

The install target must hand `pip` one explicit wheel filename, not
a glob. The chosen recipe derives the wheel path from the Makefile's
`$(VERSION)` and resolves it at recipe execution time (after `build`
has produced the wheel):

```make
deploy-tui: build
	@WHEEL=$$(ls $(OUTDIR)/$(PROJECT)-$(VERSION)-*.whl 2>/dev/null | head -1); \
	if [ -z "$$WHEEL" ]; then \
		echo "no wheel matching $(PROJECT)-$(VERSION)-*.whl in $(OUTDIR)" >&2; \
		exit 1; \
	fi; \
	pip install $$WHEEL
```

- `$(VERSION)` is a single value per project, so only one wheel
  matches the glob regardless of how many accumulate in `/srv/repo/`.
- `ls ... | head -1` runs at recipe time, after `build` has dropped
  the wheel — avoids stale-file or empty-glob issues from Make's
  parse-time variable expansion.
- Loud error message if the wheel isn't there, instead of pip
  silently failing.
- `--dev` variant replaces `pip install $$WHEEL` with
  `pip install -e <source-tree>` (independent of `OUTDIR`).

## Per-project Makefiles: install the built wheel

[ ] **bbsengine6/Makefile** — `deploy-tui` (line 172-173) currently
    calls `$(MAKE) -C py/src install`, which `py/src/Makefile:11-12`
    resolves to `cd .. && pip install --no-cache-dir -e .` —
    editable install against `py/`, not the wheel. Change `deploy-tui`
    to depend on `build`, then use the explicit-wheel recipe above
    to install the just-built
    `/srv/repo/bbsengine6/bbsengine6-$(VERSION)-*.whl` into the
    active venv. Keep `pip install -e py/` available for `--dev`.

[ ] **bed/Makefile** — `deploy: install` (line 172) already runs
    `install-venv`, which builds wheels for `bbsengine6` and `bed`
    itself into `/tmp/bed-$$/` then installs them into
    `/var/lib/bed/venv` (line 118-122). (`getdate_next` is no longer
    built inline — pip resolves it as a transitive runtime dep of
    bbsengine6 via `bbsengine6/py/pyproject.toml`.) After Phase 0,
    the bed wheel produced by top-level `make build` lives at
    `/srv/repo/bed/bed-$(VERSION)-*.whl`. Confirm that the install
    target's inline `build --wheel` matches Phase 0's `make build`
    output, so `deploy` does not build a duplicate wheel into
    `/tmp/bed-$$/`. If `install-venv`'s inline build is kept, factor
    it into the top-level `build` target so there is one source of
    truth for the bed wheel path.

[ ] **casino/Makefile** — `deploy-tui: install` (line 104) calls
    top-level `install`, which is `$(PYTHON) -m pip install .` (line
    57). That installs from the source tree, not from the wheel just
    built by `make build` into
    `/srv/repo/casino/casino-$(VERSION)-*.whl` (after Phase 0).
    Change `deploy-tui` to depend on `build`, then use the
    explicit-wheel recipe above to install into the active venv.

## `deploy --dev` — editable install

[ ] **src/deploytool/lib.py** — add `--dev` to
    `buildargs()` (ArgumentParser). When set, the per-project Makefile
    should install in editable mode (`pip install -e ...`) so edits
    in the source tree are picked up on next interpreter start without
    a rebuild + reinstall.

[ ] **src/deploytool/lib.py** — `run_make_deploy`
    propagates `--dev` to `make` via an env var (suggested name:
    `DEPLOY_DEV=1`) so each per-project Makefile can swap
    `pip install $$WHEEL` for `pip install -e <source-tree>`.
    `--dev` is independent of `OUTDIR`: the editable install path
    is the source tree, not `/srv/repo/`.

[ ] **bbsengine6/Makefile** — honor the chosen env var: when set,
    install via `pip install -e py/`; when unset, install the
    wheel via the explicit-wheel recipe.

[ ] **bed/Makefile** — honor the chosen env var: when set, install
    via `pip install -e .` from the project root (or `src/`); when
    unset, install the wheel into `/var/lib/bed/venv`.

[ ] **casino/Makefile** — honor the chosen env var: when set,
    install via `pip install -e .` from the project root; when
    unset, install the wheel into the active venv.

[ ] **Verification** (dry-run inspection):
    - `deploy --dry-run bbsengine6.tui`        → `pip install <one explicit path under /srv/repo/bbsengine6/>`
    - `deploy --dry-run --dev bbsengine6.tui` → `pip install -e py/`
    - `deploy --dry-run bed`                   → `pip install <one explicit path under /srv/repo/bed/>`
    - `deploy --dry-run --dev bed`             → `pip install -e .`
    - `deploy --dry-run casino.tui`            → `pip install <one explicit path under /srv/repo/casino/>`
    - `deploy --dry-run --dev casino.tui`      → `pip install -e .`

[ ] **Update `VENV_LAYOUT`** in
    `src/deploytool/lib.py:55-70` once the three Makefiles
    settle — the entries for `bbsengine6`, `bed`, and `casino`
    should reflect what the new `deploy-tui` / `deploy` targets
    actually do (e.g. `bed` may drop its per-service venv in
    dev mode in favor of the active venv).
