"""Turning a surviving mutant into a falsifier scaffold — the blank-page killer.

A surviving mutant is the missing falsifier made concrete: it names a change to
the code (``and->or`` at ``orders.py:42``) that *no test distinguishes from the
real thing*. So the test that would kill it is exactly the negative proof the
code is missing — you just have to write it. The hardest part of writing it is
the blank page: *where* is the gap, and what does a test of it look like?

This module answers that, deterministically and without running anything. Given
a :class:`~celebrimbor.ratchets.mutation.Survivor` and the text of the file it
names, :func:`scaffold` builds a :class:`Proposal` — the mutant's identity, the
enclosing code, a stub test, and the recipe to check the stub actually kills the
mutant — and :func:`render` writes it out for a human to complete.

Two things it deliberately is **not**:

* It is **not a proof.** A scaffold is a dated TODO. It is written to a scratch
  directory no gate reads, it is never ratified, and it satisfies no
  ``falsified_by`` or ``negative_proof``. Generation moves the blank page; it
  does not move the gate — the completed, human-ratified test does.
* It is **not synthesis.** No LLM, no network, no randomness, no tool run. The
  same survivor and source always produce the same scaffold, byte for byte.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass

from .ratchets.mutation import Survivor

_HEADER = "DRAFTED BY celebrimbor — NOT A PROOF. Complete the test, prove it kills the mutant, then ratify."


@dataclass(frozen=True, slots=True)
class Proposal:
    """A human-completable falsifier for one surviving mutant."""

    identity: str
    """The mutant, e.g. ``src/app/orders.py:42:and->or``."""

    slug: str
    """A filesystem-safe stem derived from the identity; the scaffold's filename."""

    snippet: str
    """The enclosing callable's source (or a line window), for context."""

    stub: str
    """A pytest skeleton the human fills in — deliberately failing until completed."""

    recipe: str
    """How to confirm the finished test is a real falsifier: it must go red on the
    mutant and green on the real code."""


def slugify(identity: str) -> str:
    """A stable, filesystem-safe, *collision-free* stem for ``identity``.

    Deterministic: the same survivor always maps to the same filename, so
    re-proposing overwrites rather than duplicating. The readable stem alone is
    not enough — an all-punctuation operator (``+->-``) collapses to nothing, so
    two distinct mutants at the same ``file:line`` (``+->-`` and ``+->*``) would
    slugify identically and the second scaffold would silently overwrite the
    first, dropping a real falsifier. A short hash of the *whole* identity is
    appended so distinct identities never collide, while the readable part keeps
    the filename legible.
    """
    out: list[str] = []
    for ch in identity:
        out.append(ch.lower() if ch.isalnum() else "-")
    readable = "".join(out)
    while "--" in readable:
        readable = readable.replace("--", "-")
    readable = readable.strip("-")
    digest = hashlib.blake2s(identity.encode()).hexdigest()[:6]
    return f"{readable}-{digest}" if readable else digest


def _enclosing_source(source: str, line: int) -> str:
    """The smallest def/class enclosing ``line``, or a window if none/unparseable.

    AST-based so an ``and->or`` deep inside a method extracts the method, not the
    module — but any parse failure or a line outside every definition falls back
    to a few lines around the mutation, never an exception.
    """
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _window(lines, line)

    best: tuple[int, int] | None = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        start = node.lineno
        end = node.end_lineno or node.lineno
        if start <= line <= end and (best is None or (end - start) < (best[1] - best[0])):
            best = (start, end)
    if best is None:
        return _window(lines, line)
    return "\n".join(lines[best[0] - 1 : best[1]])


def _window(lines: list[str], line: int, radius: int = 3) -> str:
    lo = max(0, line - 1 - radius)
    hi = min(len(lines), line + radius)
    return "\n".join(lines[lo:hi])


def scaffold(survivor: Survivor, source: str) -> Proposal:
    """Build the :class:`Proposal` for ``survivor`` given the text of its file."""
    slug = slugify(survivor.identity)
    snippet = _enclosing_source(source, survivor.line)
    stub = (
        f"def test_kills_{slug.replace('-', '_')}() -> None:\n"
        f"    # Surviving mutant: {survivor.identity}\n"
        f"    # No test distinguishes `{survivor.operator}` at "
        f"{survivor.file}:{survivor.line} from the real code.\n"
        f"    # Write an assertion that observes the difference and FAILS under the mutant.\n"
        f'    raise AssertionError("TODO: complete this falsifier")\n'
    )
    recipe = (
        f"Confirm this is a real falsifier before ratifying:\n"
        f"  1. Complete the test above so it passes against the real code.\n"
        f"  2. Apply the mutant `{survivor.operator}` at {survivor.file}:{survivor.line}.\n"
        f"  3. The test MUST turn red. If it stays green, it does not kill this mutant.\n"
        f"  4. Revert the mutant; the test is green again. Now it is a proof — ratify it."
    )
    return Proposal(
        identity=survivor.identity, slug=slug, snippet=snippet, stub=stub, recipe=recipe
    )


def render(proposal: Proposal) -> str:
    """The scaffold as a human-readable Markdown document."""
    return (
        f"<!-- {_HEADER} -->\n"
        f"# Falsifier scaffold: `{proposal.identity}`\n\n"
        f"> {_HEADER}\n\n"
        f"A mutant survived here — no test tells this mutation apart from the real code, "
        f"so the code makes a claim nothing can contradict. The test that kills the mutant "
        f"is the negative proof this behaviour is missing.\n\n"
        f"## Where\n\n"
        f"```python\n{proposal.snippet}\n```\n\n"
        f"## A test to complete\n\n"
        f"```python\n{proposal.stub}```\n\n"
        f"## Prove it kills the mutant\n\n"
        f"{proposal.recipe}\n"
    )
