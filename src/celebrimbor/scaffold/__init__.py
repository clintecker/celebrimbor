"""`celebrimbor init` — scaffold the ladder into a project.

Two rules govern everything here, and both are about not betraying an adopter
who already has work in the repo:

**Never clobber.** A config section that already exists is left exactly as it
is and reported as "kept". The adopter's pins, their ignores, their
carefully-argued exception — all of it survives. ``--force`` overrides, and
even then only for sections celebrimbor itself wrote.

**Append, never rewrite.** New TOML tables go on the end of ``pyproject.toml``
as complete blocks. No parse-and-re-emit, which would silently reformat the
file and destroy every comment in it. The result is a diff an adopter can read
in one glance, which is the difference between a tool they trust and a tool
they run once.

The surface map follows the same discipline for a stronger reason: re-running
``init --surfaces`` appends only modules the map does not mention, so a
ratified row cannot be overwritten — not because the merge is careful, but
because there is no merge.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Config
from ..surface.inference import infer_rows
from ..surface.inventory import inventory
from ..surface.map import append_rows
from . import templates


@dataclass(slots=True)
class InitOutcome:
    """What init did, in enough detail to review."""

    root: Path
    written: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    surfaces_added: list[str] = field(default_factory=list)
    surfaces_skipped: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems

    def lines(self) -> list[str]:
        out: list[str] = []
        for item in self.written:
            out.append(f"  wrote    {item}")
        for item in self.kept:
            out.append(f"  kept     {item} (already present)")
        for item in self.problems:
            out.append(f"  PROBLEM  {item}")

        if self.surfaces_added:
            out.append("")
            out.append(
                f"  surface map: {len(self.surfaces_added)} module(s) pre-filled, all `inferred`"
            )
            out.append("  These rows are RED until you ratify them. That is the point:")
            out.append("  inference shrinks the job, it never manufactures green.")
            if self.surfaces_skipped:
                out.append(
                    f"  {self.surfaces_skipped} module(s) got no row — inference abstained "
                    "rather than guess. The gate names them."
                )

        out.append("")
        out.append("  next: celebrimbor gate --fast")
        return out


# Config sections init owns, and the marker that says whether one is present.
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("[tool.ruff]", templates.RUFF),
    ("[tool.mypy]", templates.MYPY),
    ("[tool.pytest.ini_options]", templates.PYTEST),
    ("[tool.coverage.run]", templates.COVERAGE),
)

_MINIMAL_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []
"""


def run_init(
    root: Path | str | None = None,
    *,
    with_surfaces: bool = False,
    force: bool = False,
) -> InitOutcome:
    """Scaffold the ladder. Idempotent: safe to re-run."""
    config = Config.load(root)
    outcome = InitOutcome(root=config.root)

    _ensure_pyproject(config, outcome)
    _write_config_sections(config, outcome, force=force)
    _write_file(config.root / ".pre-commit-config.yaml", templates.PRE_COMMIT, outcome, force=force)
    _write_known_bad(config, outcome)
    config.state_dir.mkdir(parents=True, exist_ok=True)

    if with_surfaces:
        _write_surfaces(config, outcome)

    return outcome


def _ensure_pyproject(config: Config, outcome: InitOutcome) -> None:
    path = config.root / "pyproject.toml"
    if path.exists():
        return
    name = config.root.name.replace(" ", "-").replace("_", "-").lower()
    path.write_text(_MINIMAL_PYPROJECT.format(name=name), encoding="utf-8")
    outcome.written.append("pyproject.toml")


def _write_config_sections(config: Config, outcome: InitOutcome, *, force: bool) -> None:
    """Append tool tables that are not already present.

    Presence is decided by parsing the TOML, not by string search: a
    ``[tool.ruff]`` inside a comment or a string would otherwise read as
    configured and we would silently skip writing a ruleset the adopter never
    got.
    """
    path = config.root / "pyproject.toml"
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        outcome.problems.append(f"pyproject.toml could not be parsed, so nothing was added: {exc}")
        return

    tool = data.get("tool", {})
    tool = tool if isinstance(tool, dict) else {}

    additions: list[str] = []
    for header, body in _SECTIONS:
        key = header.strip("[]").split(".")[1]
        present = key in tool
        if present and not force:
            outcome.kept.append(f"pyproject.toml {header}")
            continue
        additions.append(body)
        outcome.written.append(f"pyproject.toml {header}")

    if "celebrimbor" not in tool:
        additions.append(templates.CELEBRIMBOR.format(source=config.source))
        outcome.written.append("pyproject.toml [tool.celebrimbor]")

    if not additions:
        return

    existing = path.read_text(encoding="utf-8").rstrip("\n")
    banner = "\n\n# --- added by `celebrimbor init` ---\n"
    path.write_text(existing + "\n" + banner + "\n" + "\n".join(additions), encoding="utf-8")


def _write_file(path: Path, content: str, outcome: InitOutcome, *, force: bool) -> None:
    label = path.name
    if path.exists() and not force:
        outcome.kept.append(label)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    outcome.written.append(label)


def _write_known_bad(config: Config, outcome: InitOutcome) -> None:
    directory = config.known_bad_dir
    directory.mkdir(parents=True, exist_ok=True)
    readme = directory / "README.md"
    if not readme.exists():
        readme.write_text(templates.KNOWN_BAD_README, encoding="utf-8")
        outcome.written.append(f"{config.known_bad}/README.md")
    expected = directory / "expected.yaml"
    if not expected.exists():
        expected.write_text(templates.KNOWN_BAD_EXPECTED.format("{}"), encoding="utf-8")
        outcome.written.append(f"{config.known_bad}/expected.yaml")


def _write_surfaces(config: Config, outcome: InitOutcome) -> None:
    """Infer roles and append rows the map does not already have."""
    inv = inventory(config)
    if not inv.modules:
        outcome.problems.append(
            f"no Python modules found under {config.source!r} — set `source` in "
            "[tool.celebrimbor] if the layout is unconventional"
        )
        return

    rows = infer_rows(inv.modules)
    classifiable = {m.dotted for m in inv.modules if m.parsed and m.callables and m.dotted}
    outcome.surfaces_skipped = len(classifiable - set(rows))

    added = append_rows(config.surfaces_path, rows)
    outcome.surfaces_added = added
    if added:
        outcome.written.append(".celebrimbor/surfaces.yaml")
    else:
        outcome.kept.append(".celebrimbor/surfaces.yaml (no new modules)")
