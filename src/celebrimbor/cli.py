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
from typing import TYPE_CHECKING, Any

import click

from . import __version__
from .result import Stage

if TYPE_CHECKING:
    from .watch import Snapshot


@dataclass(frozen=True, slots=True)
class GateOptions:
    """The things `gate` can be told to do, as one object.

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
    format: str = "human"
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
@click.option("--plain", is_flag=True, help="Alias for --format=plain.")
@click.option(
    "--format",
    "format",
    type=click.Choice(["human", "plain", "agent"]),
    default="human",
    help="human (default), plain (no colour), or agent (a JSON work-item verdict).",
)
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

    # `--plain` is a back-compatible alias for `--format=plain`; an explicit
    # `--format` wins, and a bare `--plain` still selects plain.
    fmt = opts.format if opts.format != "human" else ("plain" if opts.plain else "human")

    # Emitters are imported only when chosen, so the fast stage never pays the
    # import cost of a format it did not request.
    if fmt == "agent":
        from .agent import render_agent

        click.echo(render_agent(report))
    elif fmt == "plain":
        from .reporting import render_plain

        click.echo(render_plain(report))
    else:
        from .reporting import render

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
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project root. Defaults to the current directory.",
)
def watch(root: Path | None) -> None:
    """Re-run the fast gate whenever a relevant file changes. Ctrl-C to stop.

    An inner-loop companion to `celebrimbor gate --fast`: every re-run is a full
    *cold* fast-stage run, byte-identical to the gate a pre-commit hook runs.
    That is the whole safety story — watch never claims green over a red gate,
    because it does not track green; it re-runs the real gate and prints the real
    report, on every settled change to a `.py` file under source or tests, to
    `celebrimbor.toml` / `pyproject.toml`, or to a `.celebrimbor/*.yaml` ledger.
    """
    from .config import Config
    from .watch import step

    config = Config.load(root)
    click.echo(f"celebrimbor watch — {config.root}")
    click.echo("re-running the fast gate on every change; Ctrl-C to stop.")
    _run_fast(config.root)

    def on_change(delta: set[Path]) -> None:
        click.echo("")
        click.echo("changed: " + ", ".join(sorted(str(p) for p in delta)))
        _run_fast(config.root)

    snapshot: Snapshot = _snapshot(config)
    try:
        while True:
            _sleep(_POLL_S)
            current = _settle(config, snapshot, _snapshot(config))
            snapshot = step(
                snapshot, current, source=config.source, tests=config.tests, on_change=on_change
            )
    except KeyboardInterrupt:
        click.echo("\ncelebrimbor watch — stopped.")
        sys.exit(0)


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


# -- watch: the ambient half ------------------------------------------------
#
# `watch` is the one command that polls the filesystem, so its I/O lives here in
# the CLI adapter — the role budgeted to reach for a capability without being
# handed it. The pure decisions (relevance, change detection, the loop body)
# live in `celebrimbor.watch`; these helpers only enumerate files, read mtimes,
# and sleep, then hand snapshots to that pure core.

_POLL_S = 0.4
_SETTLE_S = 0.4


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _candidate_files(config: Any) -> list[Path]:
    """Every file the watch might care about, before the pure relevance filter.

    A deliberately coarse net — the whole source and tests trees (minus compiled
    ``__pycache__``, whose churn from the gate's own imports would otherwise
    re-trigger it endlessly), the root files, and every YAML under the ledger
    directory *recursively* (so a nested baseline a fast check reads is watched),
    minus the cache for the same self-trigger reason. Narrowing it to what
    actually matters is `watch.is_relevant`'s job, kept pure and tested.
    """
    found: list[Path] = []
    for base in (config.source_dir, config.tests_dir):
        if base.is_dir():
            found.extend(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    if config.root.is_dir():
        found.extend(p for p in config.root.iterdir() if p.is_file())
    if config.state_dir.is_dir():
        found.extend(
            p
            for p in config.state_dir.rglob("*.yaml")
            if p.is_file() and "cache" not in p.relative_to(config.state_dir).parts
        )
    return found


def _snapshot(config: Any) -> dict[Path, float]:
    """The current ``{repo-relative path: mtime}`` of every candidate file."""
    root = config.root
    return {p.relative_to(root): p.stat().st_mtime for p in _candidate_files(config)}


def _settle(config: Any, previous: Snapshot, current: dict[Path, float]) -> dict[Path, float]:
    """Wait out an in-progress write, so one save triggers one re-run, not many.

    While the file set is still moving relative to the last baseline, re-poll
    after a short pause until two consecutive polls agree. Then hand the settled
    snapshot back for the pure loop body to judge.
    """
    from .watch import changed

    while changed(previous, current):
        _sleep(_SETTLE_S)
        latest = _snapshot(config)
        if latest == current:
            break
        current = latest
    return current


def _run_fast(root: Path) -> None:
    """Run the fast stage for ``root`` and render it, reusing the public gate.

    Goes through `celebrimbor.gate(stage="fast")` and `reporting.render` — the
    same run-and-render the `gate` command uses — so a watch re-run cannot drift
    from the real gate. A config or check-module edit mid-session can make the
    run itself unbuildable; that is surfaced, not swallowed, and never read as a
    pass, keeping the fail-closed contract intact between edits.
    """
    from . import gate as run_gate
    from .checks import CheckModuleError
    from .config import ConfigError
    from .reporting import render

    try:
        report = run_gate(stage="fast", root=root)
    except (ConfigError, CheckModuleError) as exc:
        click.echo(f"  gate could not run (not a pass): {exc}")
        return
    render(report)


if __name__ == "__main__":
    main()
