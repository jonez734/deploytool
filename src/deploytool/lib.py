import os
import re
import subprocess
import sys
from argparse import ArgumentParser

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
    "zoid6": [],
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
    "mistermcfeely": "/var/lib/zoid6/venv",
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
}

TARGETS = {
    "zoid6": ["www", "tui", "prod"],
    "teos": ["www", "tui"],
    "achilles": ["www", "tui"],
    "casino": ["tui", "www"],
    "article2": ["www", "tui"],
    "backuptools": ["www", "tui"],
    "deploytool": ["tui"],
    "zoidoffice": ["tui"],
    "bed": ["tui", "venv", "prod"],
    "bbsengine6": ["tui", "www"],
    "getdate_next": ["tui"],
}

# Sub-target -> actual make `deploy-*` target. Some sub-target names are
# user-facing only and don't have a 1:1 `deploy-<sub>` make rule. Applied
# by run_make_deploy() before constructing the make target name.
MAKE_TARGET_ALIASES = {
    ("bed", "tui"): "venv",
    ("getdate_next", "tui"): "venv",
}


def get_targets(base):
    return TARGETS.get(base, [])


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
    parser = ArgumentParser(usage="usage: deploy.py [options] project [project ...]")
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
    #   - Without TARGETS (e.g. `mistermcfeely`, `asimov`): no
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
            io.echo(f"{{red}}unknown project: {{bold}}{base}{{/all}}", level="error")
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
                if sub not in targets:
                    available = ", ".join(targets)
                    io.echo(
                        f"{{red}}unknown sub-target {{bold}}{project}{{/all}}; "
                        f"available: {available}",
                        level="error",
                    )
                    sys.exit(1)
                subs = [sub]
                explicit_subs.add((base, sub))
        else:
            subs = [None]

        project_info.setdefault(base, [])
        for s in subs:
            if s not in project_info[base]:
                project_info[base].append(s)

    if ambiguous:
        for base, targets in ambiguous:
            io.echo(
                f"{{red}}{{bold}}{base}{{/all}} has multiple sub-targets "
                f"({', '.join(targets)}); choose one or more, e.g. "
                f"`deploy {base}.{targets[0]}`{{/all}}",
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
    sub = MAKE_TARGET_ALIASES.get((project, sub), sub) if sub is not None else sub
    target = f"deploy-{sub}" if sub else "deploy"
    cmd = ["make", "-C", project_dir, target]
    label = f"{project}.{sub}" if sub else project

    # Always copy the operator's env so PATH and friends are preserved,
    # then control the editable-mode + dry-run vars explicitly so
    # deploytool is the sole source of truth (an operator who happens to
    # have DEPLOY_EDITABLE=1 or DEPLOY_DRY_RUN=1 in their shell does not
    # accidentally trigger that mode without passing the matching flag).
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

    dry_run = getattr(args, "dry_run", False)
    if dry_run:
        cmd.append("--dry-run")
        env["DEPLOY_DRY_RUN"] = "1"
    else:
        env.pop("DEPLOY_DRY_RUN", None)

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
