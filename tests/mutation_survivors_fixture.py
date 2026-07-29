"""An in-process mutation survivor source, for the callable-seam tests (#12).

Stands in for an app's own deterministic mutation script: it returns the current
surviving mutants as a ``frozenset[Survivor]``, which celebrimbor's
survivor-identity ratchet then gates — no mutmut.
"""

from __future__ import annotations

from celebrimbor import Survivor


def survivors() -> frozenset[Survivor]:
    return frozenset(
        {
            Survivor("src/app/a.py", 10, "and->or"),
            Survivor("src/app/b.py", 5, "True->False"),
        }
    )
