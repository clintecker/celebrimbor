"""Gates on the gates.

A harness that checks an application but not itself is asking to be trusted on
exactly the terms it refuses to extend to anyone else. These two checks close
that loop: every registered check must name something that turns it red, and
that admission must expire if it is a placeholder.
"""

from __future__ import annotations

from pathlib import Path

from ..context import Context
from ..registry import CheckSpec, check, default_registry
from ..result import CheckResult, Finding, Tier


def _is_builtin(spec: CheckSpec) -> bool:
    return getattr(spec.fn, "__module__", "").startswith("celebrimbor.")


def _resolve(root: Path, ref: str) -> bool:
    """Does a falsifier reference point at something that exists?

    References are pytest-flavoured: ``tests/negative/test_x.py::test_y``. Only
    the file part is resolved here — proving the *node* exists means running
    pytest's collector, which is a fast-tier budget we do not have. Celebrimbor's
    own suite does the stronger check on its own falsifiers, where it can.
    """
    file_part = ref.split("::", 1)[0].strip()
    if not file_part:
        return False
    return (root / file_part).exists()


@check(
    id="celebrimbor.falsifiers",
    title="every registered check names something that turns it red",
    tier=Tier.FAST,
    falsified_by="tests/negative/test_falsifier_gate.py::test_unproven_past_review_date_is_red",
)
def check_falsifiers(ctx: Context) -> CheckResult:
    """No check may exist without a falsifier, and no admission may be undated.

    Two populations, deliberately treated differently:

    * **App checks** are resolved against the adopter's repo. A path that does
      not exist is a broken promise and is red.
    * **Celebrimbor's own checks** ship in a wheel that carries no ``tests/``
      directory, so resolving their paths against an adopter's root would
      always fail — and "always fails" trains people to disable it. They are
      verified in celebrimbor's own suite instead, where the files are present.

    Expiry is checked for *both*, because a date is a date regardless of whose
    repo it sits in.
    """
    registry = default_registry()
    specs = registry.all()
    if not specs:
        return CheckResult.refused(
            "celebrimbor.falsifiers",
            "no checks are registered",
            reason=(
                "the registry is empty, so this gate has nothing to verify. An empty "
                "registry means check modules failed to import, not that all is well."
            ),
        )

    findings: list[Finding] = []
    unproven_count = 0

    for spec in specs:
        waiver = spec.unproven
        if waiver is not None:
            unproven_count += 1
            if waiver.expired():
                findings.append(
                    Finding(
                        message=(
                            f"check {spec.id!r} has had no falsifier since its review date "
                            f"({waiver.review_by.isoformat()}): {waiver.reason}"
                        ),
                        code="falsifier-expired",
                        hint=(
                            "write a negative fixture that reddens this check, or move the "
                            "review date and say why in the commit"
                        ),
                    )
                )
            continue

        if _is_builtin(spec):
            continue

        for ref in spec.falsifier_paths:
            if not _resolve(ctx.root, ref):
                findings.append(
                    Finding(
                        message=(
                            f"check {spec.id!r} claims to be falsified by {ref!r}, "
                            "which does not exist"
                        ),
                        path=Path(ref.split("::", 1)[0]),
                        code="falsifier-missing",
                        hint="a gate nobody has watched fail is a gate nobody should trust",
                    )
                )

    if findings:
        return CheckResult.failed(
            "celebrimbor.falsifiers",
            f"{len(findings)} check(s) cannot demonstrate they work",
            findings,
            remedy="every gate owes a fixture that turns it red",
        )

    detail = f"{len(specs)} check(s) registered"
    if unproven_count:
        detail += f", {unproven_count} on a dated allowlist"
    return CheckResult.passed("celebrimbor.falsifiers", f"{detail}; all falsifiers accounted for")


@check(
    id="celebrimbor.registry",
    title="the registry is internally consistent",
    tier=Tier.FAST,
    falsified_by="tests/negative/test_falsifier_gate.py::test_duplicate_check_id_is_rejected",
)
def check_registry_shape(ctx: Context) -> CheckResult:
    """Structural sanity the runner depends on.

    Cheap, and it catches the class of bug where a refactor leaves two checks
    fighting over one id — at which point one of them stops being reported and
    nobody notices, because the report still has an entry under that name.
    """
    registry = default_registry()
    findings: list[Finding] = []

    seen_titles: dict[str, str] = {}
    for spec in registry.all():
        if not spec.id.replace(".", "").replace("-", "").replace("_", "").isalnum():
            findings.append(
                Finding(
                    message=f"check id {spec.id!r} is not a dotted identifier",
                    code="registry-bad-id",
                )
            )
        prior = seen_titles.get(spec.title)
        if prior is not None:
            findings.append(
                Finding(
                    message=(
                        f"checks {prior!r} and {spec.id!r} share the title {spec.title!r}; "
                        "identical titles make a failure report ambiguous"
                    ),
                    code="registry-dup-title",
                )
            )
        seen_titles[spec.title] = spec.id

    unknown = ctx.config.disabled_checks - registry.ids()
    findings.extend(
        Finding(
            message=(
                f"config disables check {name!r}, which is not registered — "
                "either a typo or a check that has been removed"
            ),
            code="registry-unknown-disabled",
            hint="a disable that matches nothing silently protects nothing",
        )
        for name in sorted(unknown)
    )

    if findings:
        return CheckResult.failed(
            "celebrimbor.registry",
            f"{len(findings)} registry defect(s)",
            findings,
        )
    return CheckResult.passed(
        "celebrimbor.registry", f"{len(registry)} check(s), ids and titles unique"
    )
