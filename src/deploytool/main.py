from bbsengine6 import io

from . import lib


def buildargs(args, **kwargs):
    return lib.buildargs(args, **kwargs)


def init(args, **kwargs) -> bool:
    return True


def access(args, op, **kwargs) -> bool:
    return True


def main(args, **kwargs):
    projects = lib.resolve(args.projects)

    # Group subs by base so callers see what's being built per project
    # (e.g. "bbsengine6 (tui, www)" rather than two flat entries).
    grouped = []
    current_base = None
    for project, sub in projects:
        if project != current_base:
            grouped.append((project, []))
            current_base = project
        grouped[-1][1].append(sub)

    order_parts = []
    for base, subs in grouped:
        if any(s is None for s in subs):
            order_parts.append(base)
        else:
            order_parts.append(f"{base} ({', '.join(subs)})")
    io.echo(f"{{bold}}deploy order:{{/all}} {', '.join(order_parts)}")

    for project, sub in projects:
        label = f"{project}.{sub}" if sub else project
        io.echo(f"\n{{bold}}=== {label} ==={{/all}}")
        rc = lib.run_make_deploy(args, project, sub)
        if rc != 0:
            io.echo(
                f"deploy failed for {{bold}}{label}{{/all}}",
                level="error",
            )
            return 1

    if getattr(args, "verify", False):
        io.echo(f"\n{{bold}}=== verify ==={{/all}}")
        project_names = [name for name, _ in projects]
        lib.run_verify(args, project_names)

    io.echo(f"\n{{green}}deploy complete{{/all}}")
    return 0
