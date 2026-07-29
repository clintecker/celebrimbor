"""Tests for the pure core of `celebrimbor watch`.

Everything here drives the change-detection logic directly — the relevance
filter, the snapshot diff, and a single iteration of the loop body — with the
loop that never ends deliberately left to the CLI adapter. A watch that could
only be tested by running it forever would be a watch nobody tests.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from celebrimbor.watch import changed, is_relevant, step

# ---------------------------------------------------------------------------
# changed(): what moved between two polls
# ---------------------------------------------------------------------------


def test_changed_is_empty_when_nothing_moved() -> None:
    """The property the inner loop rests on: a quiet poll does nothing."""
    snap = {Path("src/a.py"): 1.0, Path("src/b.py"): 2.0}
    assert changed(snap, dict(snap)) == set()


def test_changed_detects_a_modified_file() -> None:
    old = {Path("src/a.py"): 1.0}
    new = {Path("src/a.py"): 2.0}
    assert changed(old, new) == {Path("src/a.py")}


def test_changed_detects_an_added_file() -> None:
    old = {Path("src/a.py"): 1.0}
    new = {Path("src/a.py"): 1.0, Path("src/b.py"): 5.0}
    assert changed(old, new) == {Path("src/b.py")}


def test_changed_detects_a_removed_file() -> None:
    old = {Path("src/a.py"): 1.0, Path("src/b.py"): 5.0}
    new = {Path("src/a.py"): 1.0}
    assert changed(old, new) == {Path("src/b.py")}


def test_changed_reports_every_moved_path_at_once() -> None:
    old = {Path("src/a.py"): 1.0, Path("src/b.py"): 2.0}
    new = {Path("src/a.py"): 9.0, Path("src/c.py"): 3.0}
    assert changed(old, new) == {Path("src/a.py"), Path("src/b.py"), Path("src/c.py")}


# ---------------------------------------------------------------------------
# is_relevant(): which files warrant a re-run
# ---------------------------------------------------------------------------


def test_python_under_source_is_relevant() -> None:
    assert is_relevant(Path("src/pkg/mod.py"), source="src", tests="tests")


def test_python_under_tests_is_relevant() -> None:
    assert is_relevant(Path("tests/unit/test_x.py"), source="src", tests="tests")


def test_config_files_at_root_are_relevant() -> None:
    assert is_relevant(Path("celebrimbor.toml"), source="src", tests="tests")
    assert is_relevant(Path("pyproject.toml"), source="src", tests="tests")


def test_ledger_yaml_is_relevant() -> None:
    assert is_relevant(Path(".celebrimbor/surfaces.yaml"), source="src", tests="tests")
    assert is_relevant(Path(".celebrimbor/invariants.yaml"), source="src", tests="tests")


def test_python_outside_source_and_tests_is_not_relevant() -> None:
    """A `.py` elsewhere — a doc example, a scratch script — is not watched."""
    assert not is_relevant(Path("docs/snippet.py"), source="src", tests="tests")


def test_non_python_under_source_is_not_relevant() -> None:
    assert not is_relevant(Path("src/pkg/data.json"), source="src", tests="tests")
    assert not is_relevant(Path("src/pkg/mod.pyc"), source="src", tests="tests")


def test_readme_at_root_is_not_relevant() -> None:
    assert not is_relevant(Path("README.md"), source="src", tests="tests")


def test_non_yaml_in_ledger_is_not_relevant() -> None:
    assert not is_relevant(Path(".celebrimbor/notes.txt"), source="src", tests="tests")


def test_nested_baseline_is_relevant() -> None:
    """A baseline nested under the ledger dir feeds a fast check (structure), so an
    edit there moves the fast verdict and must re-run — not sit on a stale green."""
    assert is_relevant(
        Path(".celebrimbor/baselines/structure.yaml"), source="src", tests="tests"
    )


def test_ledger_cache_is_never_relevant() -> None:
    """The cache churns on every gate run; watching it would re-trigger the loop."""
    assert not is_relevant(
        Path(".celebrimbor/cache/inventory.yaml"), source="src", tests="tests"
    )


def test_relevance_honours_a_custom_source_prefix() -> None:
    assert is_relevant(Path("app/mod.py"), source="app", tests="t")
    assert not is_relevant(Path("src/mod.py"), source="app", tests="t")


# ---------------------------------------------------------------------------
# step(): one iteration of the loop body
# ---------------------------------------------------------------------------


def _spy() -> tuple[list[set[Path]], Callable[[set[Path]], None]]:
    calls: list[set[Path]] = []

    def record(delta: set[Path]) -> None:
        calls.append(delta)

    return calls, record


def test_step_reruns_when_a_watched_file_changed() -> None:
    calls, record = _spy()
    old = {Path("src/a.py"): 1.0}
    new = {Path("src/a.py"): 2.0}

    result = step(old, new, source="src", tests="tests", on_change=record)

    assert calls == [{Path("src/a.py")}]
    assert result == new  # the new snapshot becomes the next baseline


def test_step_does_nothing_when_nothing_changed() -> None:
    calls, record = _spy()
    snap = {Path("src/a.py"): 1.0}

    result = step(snap, dict(snap), source="src", tests="tests", on_change=record)

    assert calls == []
    assert result == snap


def test_step_ignores_a_change_to_an_irrelevant_file() -> None:
    """A moved but irrelevant file must not fire the gate — the filter is live."""
    calls, record = _spy()
    old = {Path("README.md"): 1.0}
    new = {Path("README.md"): 2.0}

    step(old, new, source="src", tests="tests", on_change=record)

    assert calls == []


def test_step_fires_once_for_a_mixed_change_set() -> None:
    """A relevant and an irrelevant edit in the same poll: fire, on the .py only."""
    calls, record = _spy()
    old = {Path("src/a.py"): 1.0, Path("README.md"): 1.0}
    new = {Path("src/a.py"): 2.0, Path("README.md"): 2.0}

    step(old, new, source="src", tests="tests", on_change=record)

    assert calls == [{Path("src/a.py")}]
