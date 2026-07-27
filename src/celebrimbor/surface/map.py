"""The surface map: roles by module, with per-callable overrides.

Shape of ``.celebrimbor/surfaces.yaml``::

    version: 1
    modules:
      myapp.parsing:
        role: parser
        status: inferred          # red until this says `ratified`
      myapp.render:
        role: producer
        status: ratified
        overrides:
          debug_dump:
            role: pure
            status: ratified
    exemptions:
      myapp.util:banner:
        reason: pure string constant, no behaviour to prove
        review_by: 2026-12-01

Three properties this module exists to guarantee:

**Roles are assigned by module, overridden per callable.** Never one row per
function. A five-hundred-callable app should have a map of a few dozen lines,
because a map nobody can read is a map nobody ratifies.

**Status is data, not a comment.** The build contract describes inferred rows
as marked ``# inferred``, and the rendered file does carry that comment for
the human — but the gate keys on the ``status:`` field, because a comment does
not survive a round-trip and a guarantee that depends on comment preservation
is not a guarantee.

**Re-running init appends; it never rewrites.** :func:`append_rows` adds only
modules the file does not mention, leaving every existing byte — including the
adopter's own comments and every ratified row — untouched. That makes
"re-running init never overwrites a ratified row" true by construction rather
than by careful merge logic that could have a bug in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..roles import Role
from ..waiver import Exemption, WaiverError
from ..yamlio import YamlError, expect_mapping, load_mapping

MAP_VERSION = 1

INFERRED = "inferred"
RATIFIED = "ratified"
_VALID_STATUS = frozenset({INFERRED, RATIFIED})

_HEADER = """\
# celebrimbor surface map
#
# Each module names the ROLE its callables play, which determines the kind of
# proof they owe. Rows marked `status: inferred` were guessed from naming and
# are RED until a human ratifies them.
#
# To ratify a row: check the role is right, then change `inferred` -> `ratified`.
# That is the whole job.
#
# Modules missing from this file are RED, not absent. Inference never proposes
# `pure` or `presenter` and abstains rather than guessing, so a module of
# genuinely pure helpers gets no row here and the gate will name it. Add it by
# hand with `status: ratified` — the gate tells you the exact line.
#
# A single callable that differs from its module goes under `overrides:` as one
# line, e.g. `slugify: pure`. Overrides count as ratified: typing a specific
# role for a specific callable IS the judgment call.
#
#   pure          a property or unit test over its contract
#   parser        a unit test with malformed input that must be refused
#   normalizer    a property test covering idempotence and folding
#   verifier      a negative fixture that must turn it red
#   producer      proof through the verifier that inspects its artifact
#   orchestrator  an interaction test over its dependency edges
#   adapter       a contract test against fake and real backends
#   presenter     an integration or end-to-end run
"""


class SurfaceMapError(YamlError):
    """The surface map is unusable. Red — never fall back to a default role."""


@dataclass(frozen=True, slots=True)
class Resolution:
    """How a given callable got its role."""

    role: Role | None
    status: str
    via: str
    """``"module"``, ``"override"``, ``"exempt"``, or ``"absent"``.

    ``role`` is ``None`` only for ``absent`` and ``exempt``. An absent row has
    no role because the map never mentioned it; an exempt callable has no role
    because it owes no proof at all."""

    @property
    def ratified(self) -> bool:
        return self.status == RATIFIED

    @property
    def blocks_gate(self) -> bool:
        """True when this resolution must keep the surface audit red.

        An un-ratified row blocks. So does an absent one — that is the
        completeness guarantee: a public callable the map does not mention is a
        hole, not a pass.
        """
        if self.via == "exempt":
            return False
        return self.role is None or not self.ratified


@dataclass(frozen=True, slots=True)
class SurfaceRow:
    """One module's entry in the map."""

    module: str
    role: Role
    status: str = INFERRED
    overrides: dict[str, tuple[Role, str]] = field(default_factory=dict)
    pin: str | None = None
    """Hash of the module's role-relevant *shape*, stamped at ratification.

    Ratification is a point-in-time human judgment applied to code that keeps
    moving. Without a pin, a callable can be rewritten into something the
    ratified role no longer describes and the row stays green. The pin binds
    the judgment to the code it was made about; when the shape drifts, the row
    reverts to un-ratified. See `structure.evidence.signature` for what counts
    as a change of shape (and, more importantly, what does not)."""

    @property
    def ratified(self) -> bool:
        return self.status == RATIFIED

    def override_roles(self) -> set[Role]:
        return {role for role, _ in self.overrides.values()}


@dataclass(frozen=True, slots=True)
class SurfaceMap:
    """A parsed surface map."""

    path: Path
    rows: dict[str, SurfaceRow] = field(default_factory=dict)
    exemptions: dict[str, Exemption] = field(default_factory=dict)
    version: int = MAP_VERSION

    def __contains__(self, module: str) -> bool:
        return module in self.rows

    def modules(self) -> set[str]:
        return set(self.rows)

    def resolve(self, module: str, qualname: str) -> Resolution:
        """The role a specific callable is held to.

        Precedence: exemption, then per-callable override, then module
        default, then absent. Note that an exemption short-circuits before the
        role is even consulted — an exempted callable owes nothing, so its
        module's role is irrelevant to it.
        """
        key = f"{module}:{qualname}"
        exemption = self.exemptions.get(key)
        if exemption is not None:
            return Resolution(None, RATIFIED, "exempt")

        row = self.rows.get(module)
        if row is None:
            return Resolution(None, INFERRED, "absent")

        override = row.overrides.get(qualname)
        if override is not None:
            role, status = override
            return Resolution(role, status, "override")
        return Resolution(row.role, row.status, "module")

    def effective_roles(self, module: str) -> set[Role]:
        """Every role in play for a module: its default plus any overrides.

        The producer ledger uses this rather than the module default alone,
        which is the "producer override granularity" scar — a ``producer``
        introduced by a single per-callable override on an otherwise
        non-producer module must still be caught.
        """
        row = self.rows.get(module)
        if row is None:
            return set()
        return {row.role, *row.override_roles()}

    def unratified(self) -> list[SurfaceRow]:
        return [
            r
            for r in self.rows.values()
            if not r.ratified or any(s != RATIFIED for _, s in r.overrides.values())
        ]

    def expired_exemptions(self) -> list[Exemption]:
        return [e for e in self.exemptions.values() if e.expired()]


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def load_map(path: Path) -> SurfaceMap:
    """Parse a surface map. Raises :class:`SurfaceMapError` on any defect."""
    data = load_mapping(path, what="surface map")

    version = data.get("version", MAP_VERSION)
    if not isinstance(version, int) or version > MAP_VERSION:
        raise SurfaceMapError(
            f"{path}: surface map version {version!r} is not supported by "
            f"celebrimbor (max {MAP_VERSION})"
        )

    raw_modules = data.get("modules")
    if raw_modules is None:
        raise SurfaceMapError(f"{path}: surface map has no `modules:` section")
    modules = expect_mapping(raw_modules, where=f"{path}: modules")

    rows: dict[str, SurfaceRow] = {}
    for module, body in modules.items():
        rows[str(module)] = _parse_row(path, str(module), body)

    exemptions: dict[str, Exemption] = {}
    raw_exempt = data.get("exemptions") or {}
    for key, body in expect_mapping(raw_exempt, where=f"{path}: exemptions").items():
        try:
            waiver = Exemption.from_dict(body, subject=str(key))
        except WaiverError as exc:
            raise SurfaceMapError(f"{path}: exemption {key!r}: {exc}") from exc
        exemptions[str(key)] = waiver

    return SurfaceMap(path=path, rows=rows, exemptions=exemptions, version=int(version))


def _parse_row(path: Path, module: str, body: Any) -> SurfaceRow:
    # A bare string is the terse form: `myapp.parsing: parser`. It has no
    # place to record ratification, so it is read as inferred — terseness must
    # not be a way to skip the human.
    if isinstance(body, str):
        return SurfaceRow(module=module, role=_parse_role(path, module, body), status=INFERRED)

    mapping = expect_mapping(body, where=f"{path}: modules.{module}")
    if "role" not in mapping:
        raise SurfaceMapError(f"{path}: modules.{module} has no `role:`")

    status = str(mapping.get("status", INFERRED)).strip().lower()
    if status not in _VALID_STATUS:
        raise SurfaceMapError(
            f"{path}: modules.{module}.status must be one of "
            f"{', '.join(sorted(_VALID_STATUS))}, got {status!r}"
        )

    overrides: dict[str, tuple[Role, str]] = {}
    raw_overrides = mapping.get("overrides") or {}
    for name, ov in expect_mapping(
        raw_overrides, where=f"{path}: modules.{module}.overrides"
    ).items():
        overrides[str(name)] = _parse_override(path, module, str(name), ov)

    pin = mapping.get("pin")
    if pin is not None and not isinstance(pin, str):
        raise SurfaceMapError(f"{path}: modules.{module}.pin must be a string")

    return SurfaceRow(
        module=module,
        role=_parse_role(path, module, mapping["role"]),
        status=status,
        overrides=overrides,
        pin=pin,
    )


def _parse_override(path: Path, module: str, name: str, body: Any) -> tuple[Role, str]:
    """Parse one per-callable override.

    The terse form — ``debug_dump: pure`` — is the correction flow the build
    contract asks to be "one obvious line," so it is supported and it counts
    as ratified. That is a deliberate asymmetry with module rows: a human who
    types a specific callable's specific role *has* made the judgment call,
    and demanding they also type `status: ratified` would turn a one-line fix
    into a three-line one for no added safety. Overrides are never generated
    by inference, so nothing un-ratified can arrive by this door.
    """
    if isinstance(body, str):
        return _parse_role(path, f"{module}.{name}", body), RATIFIED
    mapping = expect_mapping(body, where=f"{path}: modules.{module}.overrides.{name}")
    if "role" not in mapping:
        raise SurfaceMapError(f"{path}: modules.{module}.overrides.{name} has no `role:`")
    status = str(mapping.get("status", RATIFIED)).strip().lower()
    if status not in _VALID_STATUS:
        raise SurfaceMapError(
            f"{path}: modules.{module}.overrides.{name}.status must be one of "
            f"{', '.join(sorted(_VALID_STATUS))}, got {status!r}"
        )
    return _parse_role(path, f"{module}.{name}", mapping["role"]), status


def _parse_role(path: Path, where: str, value: Any) -> Role:
    try:
        return Role.parse(value)
    except ValueError as exc:
        raise SurfaceMapError(f"{path}: {where}: {exc}") from exc


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def render_map(rows: dict[str, SurfaceRow], *, header: bool = True) -> str:
    """Render rows as YAML, with the ``# inferred`` marker the contract asks for.

    Hand-rendered rather than dumped through PyYAML because the marker comment
    is the thing an adopter actually sees, and ``safe_dump`` cannot emit
    comments. The output is still plain YAML that ``load_map`` round-trips.
    """
    out: list[str] = []
    if header:
        out.append(_HEADER)
    out.append(f"version: {MAP_VERSION}")
    out.append("modules:")
    if not rows:
        out.append("  {}")
    for module in sorted(rows):
        out.extend(render_row(rows[module]))
    return "\n".join(out) + "\n"


def render_row(row: SurfaceRow) -> list[str]:
    marker = "  # inferred — ratify me" if row.status == INFERRED else ""
    lines = [
        f"  {row.module}:",
        f"    role: {row.role.value}",
        f"    status: {row.status}{marker}",
    ]
    if row.pin:
        lines.append(f"    pin: {row.pin}")
    if row.overrides:
        lines.append("    overrides:")
        lines.extend(
            f"      {name}: {role.value}" for name, (role, _) in sorted(row.overrides.items())
        )
    return lines


def write_map(path: Path, rows: dict[str, SurfaceRow]) -> None:
    """Write a fresh map. Refuses to clobber an existing file."""
    if path.exists():
        raise SurfaceMapError(f"{path} already exists; use append_rows() so ratified rows survive")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_map(rows), encoding="utf-8")


def append_rows(path: Path, rows: dict[str, SurfaceRow]) -> list[str]:
    """Append modules the file does not already mention. Returns what was added.

    Existing bytes are never touched, so a ratified row cannot be overwritten
    by a re-run — not because the merge is careful, but because there is no
    merge.
    """
    if not path.exists():
        write_map(path, rows)
        return sorted(rows)

    existing = load_map(path)
    new = {m: r for m, r in rows.items() if m not in existing.rows}
    if not new:
        return []

    lines = ["", "  # --- added by `celebrimbor init --surfaces` ---"]
    for module in sorted(new):
        lines.extend(render_row(new[module]))
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return sorted(new)
