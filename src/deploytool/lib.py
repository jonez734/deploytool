import argparse
import os
import re
import subprocess
import sys

from bbsengine6 import io, module

from deploytool._version import __version__


PACKAGENAME = "deploytool"
SOURCE_BASE = "/home/opencode/data/work"
DEFAULT_HOST = "merlin"
DEFAULT_TIMEOUT_SECONDS = 600


class DeployFailed(Exception):
    """Raised when a deploy step (make subprocess or verify) exits non-zero.

    Carries the failing return code and the step's user-facing label so
    main() can surface a single, structured abort message and tests can
    assert on the failure without running real make.
    """

    def __init__(self, rc, label):
        self.rc = rc
        self.label = label
        super().__init__(f"deploy failed for {label} (rc={rc})")

# Projects that live outside {SOURCE_BASE}/{name}; resolved relative to SOURCE_BASE.
PROJECT_DIRS = {
    "article2": "yummyjam/article2",
}

DEPENDENCIES = {
    "getdate_next": [],
    "bbsengine6": [],
    "zoid6": [ "bbsengine6"],
    "teos": ["bbsengine6", "zoid6"],
    "murdermotel": ["bbsengine6", "zoid6"],
    "empyre": ["bbsengine6", "zoid6"],
    "casino": ["bbsengine6"],
    "bed": ["bbsengine6"],
    "mistermcfeely": ["bbsengine6"],
    "achilles": ["bbsengine6", "zoid6"],
    "asimov": ["bbsengine6", "zoid6"],
    "letteredolive": ["bbsengine6"],
    "zoidoffice": ["bbsengine6"],
    "article2": [],
    "backuptools": ["bbsengine6"],
    "deploytool": [],
    "atlas": [],
}

ALIASES = {
    "postoffice": "mistermcfeely",
}

_ALIAS_PATTERNS = []

ALIAS_PATTERNS = [(re.compile(pattern), canonical) for pattern, canonical in _ALIAS_PATTERNS]

# Sentinel: "the user's active venv", resolved at runtime by get_venv_layout().
VENV_USER = None

# Venv registry (project -> venv path). Registry only: deploytool does not
# plumb venv vars into `make`; per-project Makefile defaults and `pip` handle
# venv targeting. Projects not listed default to VENV_USER.
VENV_LAYOUT = {
    "zoid6": "/var/lib/zoid6/venv",
    "bed": "/var/lib/bed/venv",
    "mistermcfeely": VENV_USER,
    "bbsengine6": VENV_USER,
    "teos": "/var/lib/zoid6/venv",
    "murdermotel": "/var/lib/zoid6/venv",
    "empyre": "/var/lib/zoid6/venv",
    "casino": VENV_USER,
    "achilles": "/var/lib/zoid6/venv",
    "letteredolive": "/var/lib/zoid6/venv",
    "zoidoffice": "/var/lib/zoid6/venv",
    "atlas": "/var/lib/atlas/venv",
    "backuptools": VENV_USER,
    "deploytool": VENV_USER,
}

# `bed` is pulled in only for tui targets (the tui/WebSocket wheel requires
# bed); a www-only deploy should not force a bed rebuild.
# Sub-targets match down the chain: casino.tui -> bed.tui -> bbsengine6.tui
# so every consumer of bbsengine6's tui build sees the same artifacts.
# `bed.tui` aliases to `deploy-venv` via MAKE_TARGET_ALIASES, so the make
# target is still `deploy-venv` — the sub name just keeps the topo chain
# self-describing.
#
# `getdate-next` is declared in `bbsengine6/py/pyproject.toml` as a
# runtime dep and is resolved by pip when bbsengine6 installs. deploytool
# does NOT orchestrate a separate `getdate_next` install — getdate_next's
# local source build lives in `getdate_next/Makefile deploy-venv` for
# developer/CI use, but the deploy chain doesn't call it.
CONDITIONAL_DEPENDENCIES = {
    "zoid6": {
        "www": ["bbsengine6"],
        "tui": [("bbsengine6", "tui"), ("bed", "tui")],
    },
    "casino": {
        "www": [("bbsengine6", "www")],
        "tui": [("bed", "tui")],
    },
    "article2": {
        "tui": [("bbsengine6", "tui")],
        "www": [("bbsengine6", "www")],
    },
    "deploytool": {
        "tui": [("bbsengine6", "tui")],
    },
    "bed": {
        "tui": [("bbsengine6", "tui")],
    },
    # @since 2026-09-27 — `deploy teos.www` must land zoid6's shared
    # chrome (skin/tmpl/page.tmpl and friends) before teos's
    # vhost config. Otherwise Smarty renders page.tmpl from
    # zoid6's tree but the teos config's SHAREDPAGEMARKER define
    # (and any other shared-page-fingerprint constants) land on
    # merlin in the wrong order, producing a window where
    # curl-grep on a freshly-deployed teos URL sees the new
    # config but the old shared template -- masking whether the
    # marker or the FA Kit fix is actually live. Walking
    # ("zoid6", "shared") first ensures the topo order is
    # correct. The dependency is conditional because teos.tui
    # does NOT depend on the shared templates (the TUI deploys
    # its own bundled chrome).
    "teos": {
        "www": [
            ("zoid6", "shared"),
            # @since 2026-09-27 — `deploy teos.www` must also land the
            # bbsengine6 engine entry-points onto the zoidtechnologies.com
            # vhost (the vhost teos lives under) before teos's own vhost
            # rsync. The `("teos", "engine")` sub runs `make deploy-engine`
            # in teos/Makefile, which delegates to `bbsengine6 engine-deploy-prod`
            # (the existing stage+prod push umbrella at bbsengine6/Makefile:233-234
            # -> bbsengine6/engine/Makefile:19-20). No standalone `bbsengine6.engine-stage`
            # dep is needed because engine-deploy-prod runs the stage rule
            # internally. ENGINE_DOCROOT env var flows through the same plumbing
            # used by bbsengine6.engine-stage / bbsengine6.engine-prod; see
            # run_make_deploy below. Wired in the "www" sub only — teos.tui
            # does NOT need the engine install (the TUI doesn't render
            # engine-rendered templates).
            ("teos", "engine"),
        ],
    },
}

TARGETS = {
    "zoid6": ["www", "tui", "prod", "shared"],
    "teos": ["www", "tui", "engine"],
    "achilles": ["www", "tui"],
    "casino": ["tui", "www"],
    "article2": ["www", "tui"],
    "backuptools": ["www", "tui"],
    "deploytool": ["tui"],
    "zoidoffice": ["tui", "www"],
    "bed": ["tui", "venv", "prod"],
    "bbsengine6": ["tui", "wwworg", "wwwcom", "handbook", "handbook-prod", "engine-stage", "engine-prod"],
    "getdate_next": ["tui"],
    "mistermcfeely": ["tui", "prod"],
}

# Sub-target -> bare make target name. When a (project, sub) pair has
# an entry here, `run_make_deploy()` invokes that make target verbatim
# WITHOUT the usual `deploy-` prefix. Used for (project, sub) pairs
# whose user-facing sub name does NOT match a `deploy-<sub>` make rule
# in the project's Makefile.
#
# ("bed", "tui") -> "venv" because bed's Makefile declares `deploy-venv`
# (not `deploy-tui`); the `tui` sub is a Python venv install.
# ("getdate_next", "tui") -> "venv" — same reason.
# ("zoid6", "shared") -> "shared" because zoid6/Makefile declares the
# target as a plain `shared:` rule (not `deploy-shared:`). It rsyncs
# zoid6's shared template directory (skin/tmpl/, css/, art/) from
# STAGEDOCROOT to PRODDOCROOT on the target host. Other vhosts that
# share chrome (te.os, achilles, empyre, etc.) depend on this sub
# landing before they deploy their own vhost config; the dependency is
# wired in CONDITIONAL_DEPENDENCIES below.
#
# Applied in two places:
#   - run_make_deploy() (lib.py:~525)  — picks the make target to run.
#   - resolve() (lib.py:~460)         — used as a dedup key so two subs
#     that resolve to the same make target don't run twice.
MAKE_TARGET_ALIASES = {
    ("bed", "tui"): "venv",
    ("getdate_next", "tui"): "venv",
    ("zoid6", "shared"): "shared",
}


def get_targets(base):
    return TARGETS.get(base, [])


def resolve_sub_prefix(sub, targets):
    """Resolve a user-supplied sub string to the canonical sub name in
    `targets`, allowing the shortest unique prefix.

    Match rules (case-sensitive, prefix-anchored on `sub`):

    - Exact match wins (preserves the historical contract for every
      existing sub name — `tui`, `wwworg`, `handbook`, `prod`, ...).
    - Otherwise: exactly one entry in `targets` starts with `sub` →
      that entry is returned (shortest unique prefix within this base).
    - Zero entries match → returns `None` ("unknown sub-target";
      caller emits the existing error message).
    - More than one entry starts with `sub` → returns a 2-tuple
      `(None, [matches...])` so the caller can emit a distinct
      ambiguous-prefix error listing the matches.

    This is **not** a fuzzy match: typos like `hanbook` still error.
    Per-base scoping means a prefix that resolves to `prod` in
    `zoid6` does not leak into other projects whose `TARGETS`
    happen to also contain a `prod`.

    Returns either:
      - `str` — the canonical sub name (exact or unique prefix)
      - `None` — no match
      - `(None, list[str])` — ambiguous prefix; `list` is the
        set of candidate subs that started with `sub`, in
        `TARGETS` order.
    """
    if sub in targets:
        return sub
    matches = [t for t in targets if t.startswith(sub)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return (None, matches)
    return None


def get_venv_layout(base: str) -> str:
    canonical: str = ALIASES.get(base, base)
    venv = VENV_LAYOUT.get(canonical, VENV_USER)
    if venv is not None:
        return venv
    active = os.environ.get("VIRTUAL_ENV")
    if active:
        return active
    if sys.prefix != sys.base_prefix:
        return sys.prefix
    io.echo(
        "{red}no active venv: {bold}activate a virtualenv before deploying{/all}",
        level="error",
    )
    sys.exit(1)


def runmodule(args, modulename, **kwargs):
    return module.runmodule(args, f"{PACKAGENAME}.{modulename}", **kwargs)


def buildargs(args=None, **kwargs):
    parser = argparse.ArgumentParser(usage="usage: deploy.py [options] project [project ...]")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", help="debug mode")
    parser.add_argument("projects", nargs="+", help="project names to deploy")
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="target host (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print commands without executing",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="per-step subprocess timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="run verification after deploy",
    )
    parser.add_argument(
        "--editable",
        action="store_true",
        help="install in editable mode (pip install -e); DEPLOY_EDITABLE=1 "
             "is exported to make so per-project Makefiles can swap wheel "
             "install for editable install",
    )
    parser.add_argument(
        "--with-deps",
        action="store_true",
        help="include transitive dependencies in the deploy chain. "
             "Without this flag, only explicitly named projects are "
             "deployed (no transitive deps are pulled in). "
             "Bare-base invocation (`deploy foo` with no `.sub`) is "
             "ambiguous whenever `TARGETS[foo]` has more than one entry, "
             "regardless of this flag; the resolver lists the subs and "
             "exits 1. Name a sub explicitly (e.g. `deploy casino.tui`) "
             "to avoid the ambiguity. (default: %(default)s)",
    )
    parser.add_argument(
        "--upgrade",
        action=argparse.BooleanOptionalAction,
        default=True,
        dest="upgrade",
        help="pass `--upgrade` to every `pip install` in the deploy chain. "
             "Default: enabled (the deploy will `pip install --upgrade ...` "
             "for each project wheel and its runtime deps, so transitive "
             "deps track their PyPI releases between deploys). Pass "
             "`--no-upgrade` to restore the prior behavior of pinning "
             "transitive deps to whatever was already in the target venv "
             "(useful when the deploy must be hermetic and reproducible "
             "against the wheels in $(OUTDIR) only). Sets `DEPLOY_UPGRADE=1` "
             "in the subprocess env when enabled; per-project Makefiles "
             "read `DEPLOY_UPGRADE` and add `--upgrade` to their `pip install` "
             "lines accordingly.",
    )
    return parser


def resolve(projects, with_deps=False):
    # Parse and validate all project names first.
    # project_info: base -> list of requested subs (one entry per sub-target).
    # Projects without TARGETS get a single [None] entry meaning "bare deploy".
    #
    # Bare-base rules:
    #   - With TARGETS and no sub named, AND multiple subs in TARGETS:
    #     AMBIGUOUS — list the subs and exit 1. Caller must name a sub
    #     (e.g. `deploy casino.tui`). `--with-deps` does NOT change this;
    #     the flag only controls dep walking, not sub expansion.
    #   - With TARGETS and no sub named, AND exactly one sub in TARGETS:
    #     auto-pick that single sub (no ambiguity possible). E.g.
    #     `deploy getdate_next` -> `getdate_next.tui`.
    #   - Without TARGETS (e.g. `asimov`, `letteredolive`, `atlas`): no
    #     ambiguity; runs the bare `make deploy` target.
    project_info = {}
    # Subs the caller (or a transitive explicit dep) named explicitly.
    # Used below to keep auto-expanded `prod` sub-targets out of the
    # default deploy — `prod` is the sudo umbrella install and should
    # only run when explicitly requested.
    explicit_subs = set()
    ambiguous = []  # bare bases with TARGETS that did NOT get auto-picked
    for project in projects:
        parts = project.split(".", 1)
        base = parts[0]
        sub = parts[1] if len(parts) > 1 else None

        if base in ALIASES:
            base = ALIASES[base]
        else:
            for pattern, canonical in ALIAS_PATTERNS:
                if pattern.match(base):
                    base = canonical
                    break

        if base not in DEPENDENCIES:
            io.echo(f"unknown project: {{bold}}{base}", level="error")
            sys.exit(1)

        targets = get_targets(base)
        if targets:
            if sub is None:
                if len(targets) == 1:
                    subs = list(targets)
                    explicit_subs.add((base, subs[0]))
                else:
                    ambiguous.append((base, targets))
                    subs = []
            else:
                resolved = resolve_sub_prefix(sub, targets)
                if isinstance(resolved, tuple):
                    # Ambiguous prefix: multiple TARGETS entries start
                    # with `sub`. Surface a distinct error so the caller
                    # knows the sub string wasn't unknown — it matched
                    # too many. Listing the matches preserves the
                    # existing "available: ..." shape.
                    matches = resolved[1]
                    available = ", ".join(targets)
                    matches_str = ", ".join(matches)
                    io.echo(
                        f"ambiguous sub-target prefix {{bold}}{project}; "
                        f"`{sub}` matches: {matches_str} "
                        f"(available: {available})",
                        level="error",
                    )
                    sys.exit(1)
                if resolved is None:
                    available = ", ".join(targets)
                    io.echo(
                        f"unknown sub-target {{bold}}{project}; "
                        f"available: {available}",
                        level="error",
                    )
                    sys.exit(1)
                subs = [resolved]
                explicit_subs.add((base, resolved))
        else:
            subs = [None]

        project_info.setdefault(base, [])
        for s in subs:
            if s not in project_info[base]:
                project_info[base].append(s)

    if ambiguous:
        for base, targets in ambiguous:
            io.echo(
                f"{{bold}}{base} has multiple sub-targets "
                f"({', '.join(targets)}); choose one or more, e.g. "
                f"`deploy {base}.{targets[0]}`",
                level="error",
            )
        sys.exit(1)

    # Topological sort
    visited = set()
    order = []

    def _normalize_dep(dep):
        if isinstance(dep, tuple):
            return dep
        return (dep, None)

    requested_subs = {}
    for base, subs in project_info.items():
        requested_subs.setdefault(base, set()).update(subs)

    def visit(name, sub=None, explicit=False):
        if (name, sub) in visited:
            return
        visited.add((name, sub))
        if explicit and sub is not None:
            project_info.setdefault(name, [])
            if sub not in project_info[name]:
                project_info[name].append(sub)
            requested_subs.setdefault(name, set()).add(sub)
            explicit_subs.add((name, sub))
        if with_deps:
            for dep in DEPENDENCIES.get(name, []):
                visit(dep)
            for cond_sub, extra_deps in CONDITIONAL_DEPENDENCIES.get(name, {}).items():
                if cond_sub in requested_subs.get(name, set()):
                    for dep in extra_deps:
                        dep_name, dep_sub = _normalize_dep(dep)
                        visit(dep_name, dep_sub, explicit=(dep_sub is not None))
        order.append((name, sub))

    seed = []
    for base, subs in project_info.items():
        for s in subs:
            # Only subs the user (or a transitive explicit dep) explicitly
            # named are explicit. Auto-expanded subs (from `deploy foo`
            # with no sub) are not explicit, which keeps `prod` out of
            # the default deploy.
            seed.append((base, s, (base, s) in explicit_subs))
    for base, sub, is_explicit in seed:
        visit(base, sub, explicit=is_explicit)

    # Deduplicate. If a base appears both with a sub and with sub=None,
    # drop the sub=None entry. Preserve topological order.
    has_sub = {name for name, sub in order if sub is not None}
    seen = set()
    deduped = []
    for name, sub in order:
        if sub is None and name in has_sub:
            continue
        if (name, sub) in seen:
            continue
        seen.add((name, sub))
        deduped.append((name, sub))

    # Resolve aliases (e.g. bed.tui -> bed.venv) and dedup at the
    # make-target level so two subs that resolve to the same `deploy-*`
    # target don't run twice. Preserve the user-facing sub name in the
    # output (the first one encountered wins). Also drop auto-expanded
    # `prod` subs — `prod` is opt-in (sudo umbrella install).
    seen_targets = set()
    final = []
    for name, sub in deduped:
        if sub == "prod" and (name, sub) not in explicit_subs:
            continue
        resolved = MAKE_TARGET_ALIASES.get((name, sub), sub) if sub is not None else None
        key = (name, resolved)
        if key in seen_targets:
            continue
        seen_targets.add(key)
        final.append((name, sub))

    return final


def _run_subprocess(cmd, *, cwd=None, timeout, env=None, label):
    """Run `cmd` with subprocess hardening; raise DeployFailed on failure.

    Contract:
      - returns (returncode, stdout, stderr) on success
      - raises DeployFailed(rc=-1, label) on TimeoutExpired, FileNotFoundError,
        OSError, or any non-zero returncode
      - does NOT catch KeyboardInterrupt or SystemExit — let them propagate
      - uses encoding="utf-8" + errors="replace" so non-UTF8 subprocess
        output can't crash the parent with UnicodeDecodeError
      - uses start_new_session=True so the child has its own process group,
        which makes cleanup on signal more reliable
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            check=False,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as e:
        io.echo(
            f"{{bold}}{label}{{/all}} timed out after {timeout}s: {' '.join(cmd)}",
            level="error",
        )
        raise DeployFailed(-1, label) from e
    except FileNotFoundError as e:
        io.echo(
            f"{{bold}}{label}{{/all}} command not found: {e.filename or e}",
            level="error",
        )
        raise DeployFailed(-1, label) from e
    except OSError as e:
        io.echo(f"{{bold}}{label}{{/all}} OS error: {e}", level="error")
        raise DeployFailed(-1, label) from e

    if result.returncode != 0:
        io.echo(
            f"{{bold}}{label}{{/all}} exited with rc={result.returncode}",
            level="error",
        )
        if result.stderr:
            io.echo(result.stderr, level="error")
        raise DeployFailed(result.returncode, label)

    return result


def run_make_deploy(args, project, sub=None):
    """Run `make deploy[-sub]` for `project.sub`; abort the deploy on failure.

    Returns 0 on success. Raises DeployFailed(rc, label) on any non-zero
    subprocess exit, timeout, or environment error. KeyboardInterrupt and
    SystemExit propagate to the caller.
    """
    project_dir = f"{SOURCE_BASE}/{PROJECT_DIRS.get(project, project)}"
    # When the (project, sub) pair has a MAKE_TARGET_ALIASES entry, the
    # alias value is the bare make target name (e.g. zoid6's `shared` rule
    # is a plain `shared:`, not `deploy-shared:`) — use it verbatim
    # without the `deploy-` prefix. Otherwise fall back to the default
    # `deploy-<sub>` shape.
    if sub is not None and (project, sub) in MAKE_TARGET_ALIASES:
        target = MAKE_TARGET_ALIASES[(project, sub)]
    else:
        sub = MAKE_TARGET_ALIASES.get((project, sub), sub) if sub is not None else sub
        target = f"deploy-{sub}" if sub else "deploy"
    cmd = ["make", "-C", project_dir, target]
    label = f"{project}.{sub}" if sub else project

    # Always copy the operator's env so PATH and friends are preserved,
    # then control the editable-mode + with-deps + dry-run vars
    # explicitly so deploytool is the sole source of truth (an operator
    # who happens to have DEPLOY_EDITABLE=1, DEPLOY_WITH_DEPS=1, or
    # DEPLOY_DRY_RUN=1 in their shell does not accidentally trigger that
    # mode without passing the matching flag).
    env = os.environ.copy()
    if getattr(args, "editable", False):
        env["DEPLOY_EDITABLE"] = "1"
    else:
        # Strip every editable-mode var (canonical + legacy aliases bed
        # accepts) so the per-project Makefile falls back to its wheel
        # install path. EDITABLE/DEV are bed's existing names — once
        # bed/Makefile is updated to honor them under DEPLOY_EDITABLE,
        # this strip keeps the operator from accidentally triggering
        # editable mode via a stale shell var.
        for var in ("DEPLOY_EDITABLE", "EDITABLE", "DEV"):
            env.pop(var, None)

    # --with-deps plumbing: per-project Makefiles (specifically
    # bbsengine6/py/src/Makefile precheck-editable) read
    # DEPLOY_WITH_DEPS to decide whether to hard-fail or warn-and-
    # proceed on an editable-in-venv precondition. The flag is
    # also a no-op for projects that don't read it, which is the
    # whole point — extend the contract per-project without
    # coupling deploytool to any project's invocation semantics.
    # Match the DEPLOY_EDITABLE pattern: set explicitly when the
    # matching CLI flag is passed, strip (rather than preserve) when
    # not, so a stray shell var can't accidentally flip a Makefile
    # out of its default branch.
    if getattr(args, "with_deps", False):
        env["DEPLOY_WITH_DEPS"] = "1"
    else:
        env.pop("DEPLOY_WITH_DEPS", None)

    # ENGINE_DOCROOT plumbing: per-vhost /engine/ install override for
    # bbsengine6.engine-stage / bbsengine6.engine-prod / teos.engine. The
    # operator passes ENGINE_DOCROOT=... in their shell; deploytool reads
    # it from os.environ and exports to the make subprocess so the ?=
    # defaults in bbsengine6/Makefile (parent, exported to sub-makes) and
    # bbsengine6/engine/Makefile (sub-make) resolve to the operator's path
    # instead of the zoidtechnologies.com default. Set/strip semantics
    # mirror DEPLOY_EDITABLE: set when the operator passes the var, strip
    # when unset so a stale shell var can't silently redirect /engine/ to
    # the wrong vhost. No-op for any (project, sub) that doesn't read it
    # (other subs ignore the env var). No CLI flag — env var only, matching
    # the existing DEPLOY_* plumbing contract.
    if "ENGINE_DOCROOT" in os.environ:
        env["ENGINE_DOCROOT"] = os.environ["ENGINE_DOCROOT"]
    else:
        env.pop("ENGINE_DOCROOT", None)

    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        cmd.append("--dry-run")
        env["DEPLOY_DRY_RUN"] = "1"
    else:
        env.pop("DEPLOY_DRY_RUN", None)

    # DEPLOY_UPGRADE plumbing: per-project Makefiles read DEPLOY_UPGRADE
    # and add `--upgrade` to their `pip install` lines when it equals 1.
    # Inverted default vs DEPLOY_EDITABLE / DEPLOY_WITH_DEPS: those are
    # opt-in flags, so they're set to "1" when the matching CLI flag is
    # passed and stripped when it isn't. `--upgrade` is opt-out (default
    # true) so the logic is the same shape — set when enabled, strip
    # when disabled — but `getattr(args, "upgrade", True)` defaults to
    # True instead of False, matching argparse's `BooleanOptionalAction`
    # default. This keeps a stale shell var from silently downgrading a
    # fresh deploy: if the operator passed nothing and has
    # `DEPLOY_UPGRADE=` (empty) in their shell, the strip branch leaves
    # the env empty and per-project Makefiles' `ifeq ($(DEPLOY_UPGRADE),1)`
    # falls through to the non-upgrade branch, matching the CLI intent.
    if getattr(args, "upgrade", True):
        env["DEPLOY_UPGRADE"] = "1"
    else:
        env.pop("DEPLOY_UPGRADE", None)

    if dry_run:
        io.echo(f"{{yellow}}dry-run:{{/all}} {' '.join(cmd)}")
    else:
        io.echo(f"{{cyan}}running:{{/all}} {' '.join(cmd)}")
    timeout = getattr(args, "timeout", DEFAULT_TIMEOUT_SECONDS)
    result = _run_subprocess(cmd, timeout=timeout, env=env, label=label)
    if result.stdout:
        io.echo(result.stdout)
    return 0


def run_verify(args, projects):
    """Run the post-deploy verification step; abort on non-zero exit.

    Today only `bbsengine6` has a verify step (`php test_blurb_render.php`
    in `bbsengine6/php/`). Same exception contract as run_make_deploy:
    returns 0 on success, raises DeployFailed on any non-zero exit,
    timeout, or environment error. Skips silently when `bbsengine6` is
    not in `projects`.
    """
    if "bbsengine6" not in projects:
        return 0
    label = "verify.bbsengine6"
    cmd = ["php", "test_blurb_render.php"]
    project_dir = f"{SOURCE_BASE}/bbsengine6/php"
    timeout = getattr(args, "timeout", DEFAULT_TIMEOUT_SECONDS)

    if getattr(args, "dry_run", False):
        io.echo(f"{{yellow}}dry-run:{{/all}} {' '.join(cmd)} (cwd={project_dir})")
        return 0

    io.echo(f"{{cyan}}running:{{/all}} {' '.join(cmd)} (cwd={project_dir})")
    _run_subprocess(cmd, cwd=project_dir, timeout=timeout, label=label)
    io.echo("{green}verification passed{/all}")
    return 0
