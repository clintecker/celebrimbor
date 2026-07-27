"""Structural discipline: complexity, injected dependencies, cohesion, layering.

These gates answer a different question from the obligation engine. The
obligation engine asks *has this callable earned trust?*; the structure engine
asks *is this callable shaped so it could?* A two-hundred-line function with
nesting depth seven and an ambient clock cannot be meaningfully proved by any
test, so demanding a proof of it is demanding a fiction.

Structure therefore runs first and cheaply, in Tier 0, and mostly without
needing the role map. The one gate that does need roles — the capability
budget — is the sharpest of them, because a role turns a vague "inject your
dependencies" into a falsifiable claim about a specific callable.
"""

from __future__ import annotations

from ..limits import Limits
from .capabilities import (
    ROLE_BUDGET,
    AmbientUse,
    BudgetViolation,
    Capability,
    scan_callable,
    violations,
)
from .complexity import CallableMetrics, ModuleMetrics, measure_module

__all__ = [
    "ROLE_BUDGET",
    "AmbientUse",
    "BudgetViolation",
    "CallableMetrics",
    "Capability",
    "Limits",
    "ModuleMetrics",
    "measure_module",
    "scan_callable",
    "violations",
]
