"""The command line: `celebrimbor init` and `celebrimbor gate`.

Two commands. The build contract calls the whole product surface "near-zero
wiring," and a CLI that grows subcommands is a CLI that has started asking the
adopter to learn it.

Imports are deliberately deferred. ``click`` and ``rich`` together cost most of
a tenth of a second at import, the fast stage has a ~10s budget, and none of
that budget should go to code that only formats output.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click

from . import __version__
from .result import Stage


@dataclass(frozen=True, slots=True)
class GateOptions:
    """The seven things `gate` can be told to do.

    A named concept rather than seven positional parameters, which is exactly
    the remedy celebrimbor's own complexity gate suggests for a long parameter
    list. Click still declares each option; it just hands them over as one
    object, so the signature stays honest about there being *one* input here —
    a description of the run.
    """

    stage_flag: str | None = None
    root: Path | None = None
    diff_base: str | None = None
    verbose: bool = False
    plain: bool = False
    update_baselines: bool = False
    reason: str | None = None


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="celebrimbor")
def main() -> None:
    """Invariant-driven design as a framework.

    Every unit carries its own falsifier; the gate fails closed.
    """


@main.command()
@click.option(
    "--surfaces",
    is_flag=True,
    help="Also infer roles and write a pre-filled, ratify-me surface map (obligation gates).",
)
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project root. Defaults to the current directory.",
)
@click.option("--force", is_flag=True, help="Overwrite tool configs this command owns.")
def init(surfaces: bool, root: Path | None, force: bool) -> None:
    """Scaffold the quality ladder into this project.

    Writes opinionated defaults for ruff, mypy, the formatter and pytest, a
    pre-commit hook whose one entry is `celebrimbor gate --fast`, and a
    `tests/known-bad/` directory.

    Ratified rows in an existing surface map are never touched: re-running
    appends only modules the map does not already mention.
    """
    from .scaffold import run_init

    outcome = run_init(root=root, with_surfaces=surfaces, force=force)
    for line in outcome.lines():
        click.echo(line)
    sys.exit(0 if outcome.ok else 1)


@main.command()
@click.option("--fast", "stage_flag", flag_value="fast", help="Pre-commit stage (~10s).")
@click.option("--full", "stage_flag", flag_value="full", help="Merge/release stage.")
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project root. Defaults to the current directory.",
)
@click.option("--diff-base", default=None, help="Git ref the impact gate diffs against.")
@click.option("-v", "--verbose", is_flag=True, help="Show hints, skips and full findings.")
@click.option("--plain", is_flag=True, help="No colour; for logs and CI annotations.")
@click.option(
    "--update-baselines",
    is_flag=True,
    help="Re-baseline ratchets. Requires --reason and a pinned environment.",
)
@click.option("--reason", default=None, help="Why a baseline is being moved. Recorded.")
def gate(**options: Any) -> None:
    """Run the gate. Exit 0 only if every check that ran proved its claim.

    \b
      --fast    lint, types, format, known-bad, surface     (~10s)
      (default) + coverage ratchet, invariants, impact      (~2min)
      --full    + mutation, container/integration steps
    """
    from .checks import CheckModuleError, load_check_modules
    from .context import Context
    from .reporting import render, render_plain
    from .runner import load_builtin_checks, run

    opts = GateOptions(**options)
    if opts.update_baselines and not opts.reason:
        raise click.UsageError(
            "--update-baselines requires --reason. A floor that moves without a "
            "written reason is a floor that will keep moving."
        )

    stage = Stage.parse(opts.stage_flag or "default")
    load_builtin_checks()
    ctx = Context.for_root(
        opts.root,
        stage=stage,
        diff_base=opts.diff_base,
        update_baselines=opts.update_baselines,
        update_reason=opts.reason,
    )
    # The app's own @check modules, so `celebrimbor gate` runs them too. A module
    # that will not import is a hard error, not a silently smaller gate.
    try:
        load_check_modules(ctx.config.check_modules)
    except CheckModuleError as exc:
        raise click.ClickException(str(exc)) from exc
    report = run(ctx)

    if opts.plain:
        click.echo(render_plain(report))
    else:
        render(report, verbose=opts.verbose)
    sys.exit(report.exit_code)


@main.command()
@click.argument("modules", nargs=-1)
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project root. Defaults to the current directory.",
)
@click.option("--all", "ratify_all", is_flag=True, help="Ratify every row in the map.")
def ratify(modules: tuple[str, ...], root: Path | None, ratify_all: bool) -> None:
    """Confirm surface-map rows and pin them to the current code.

    Ratification has two halves and only one is yours: deciding the role is a
    judgment, stamping the shape-pin is arithmetic. This does the arithmetic so
    the pin is never absent — and an absent pin is the drift hole it exists to
    close.

    Naming no modules and passing no --all is an error rather than a
    convenience default: "ratify everything I have not looked at" is exactly
    the action nobody should take by accident.
    """
    from .checks.evidence import compute_pin
    from .config import Config
    from .surface.inventory import inventory
    from .surface.ratify import apply

    if not modules and not ratify_all:
        raise click.UsageError(
            "name the module(s) to ratify, or pass --all. Ratifying by accident "
            "is the one thing this command must not make easy."
        )

    config = Config.load(root)
    if not config.surfaces_path.exists():
        raise click.UsageError(
            f"no surface map at {config.surfaces_path}. Run `celebrimbor init --surfaces` first."
        )

    inv = inventory(config)
    pins = {
        module.dotted: pin
        for module in inv.modules
        if module.dotted and (pin := compute_pin(module)) is not None
    }
    outcome = apply(config.surfaces_path, pins, only=set(modules) if modules else None)
    for line in outcome.lines():
        click.echo(line)
    sys.exit(0 if outcome.ok else 1)


@main.command()
def explain() -> None:
    """Print the role taxonomy, capability budget and registered checks.

    Exists because a convention nobody can see is configuration with extra
    steps. Everything this prints is derived from the same tables the gates
    read, so it cannot drift from what is actually enforced.
    """
    from .docs import budget_table, role_table
    from .registry import Family, default_registry
    from .runner import load_builtin_checks

    load_builtin_checks()
    click.echo("\n## Role obligations\n")
    click.echo(role_table())
    click.echo("\n## Capability budget (what each role may reach for)\n")
    click.echo(budget_table())
    click.echo("\n## Registered checks\n")
    for spec in default_registry():
        marker = " [obligation]" if spec.family is Family.OBLIGATION else ""
        falsifier = spec.unproven or ", ".join(spec.falsifier_paths)
        click.echo(f"  {spec.stage.label:<8} {spec.id}{marker}")
        click.echo(f"           {spec.title}")
        click.echo(f"           [dim]falsified by: {falsifier}")
    click.echo()


if __name__ == "__main__":
    main()
