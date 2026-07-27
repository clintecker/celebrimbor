"""Ratchets: committed baselines that may only improve.

A ratchet is a number (or a set) recorded in the pinned environment, committed
to the repo, and thereafter allowed to move in one direction only. Coverage may
rise; it may not fall. The set of surviving mutants may shrink; it may not gain
a member.

Three rules hold across every ratchet here, and all three are scars:

* **Baseline only in the pinned environment.** A dev box measures higher than
  CI — different Python, different installed extras, different luck in what
  gets imported — so a dev-box baseline hands the adopter a red CI on day two.
  The baseline records where it was taken and the write path refuses a dev box.
* **No silent lowering.** The only way a floor moves down is ``--update`` with
  a written reason, in the pinned environment. There is no local path that can
  quietly weaken a ratchet.
* **A weak floor is not a green floor.** A floor recorded below the configured
  threshold is red until a human writes why (the low-floor meta-ratchet), so
  auto-baselining cannot freeze poor coverage as false green.
"""

from __future__ import annotations

from .baseline import BaselineEnvironmentError, RatchetError
from .coverage import CoverageBaseline, coverage_regressions, load_coverage_baseline
from .mutation import MutationBaseline, Survivor, load_mutation_baseline, new_survivors

__all__ = [
    "BaselineEnvironmentError",
    "CoverageBaseline",
    "MutationBaseline",
    "RatchetError",
    "Survivor",
    "coverage_regressions",
    "load_coverage_baseline",
    "load_mutation_baseline",
    "new_survivors",
]
