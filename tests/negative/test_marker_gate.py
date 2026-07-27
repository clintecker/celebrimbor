"""Negative fixtures for the marker-grammar gate.

Every test here asserts — which is the grammar the gate enforces, so these
fixtures are also a small proof that celebrimbor's own suite obeys it.
"""

from __future__ import annotations

import pytest

from celebrimbor.result import Verdict
from tests.conftest import Project

pytestmark = pytest.mark.negative

_ID = "celebrimbor.markers"


def codes(result: object) -> set[str]:
    return {f.code for f in result.findings if f.code}  # type: ignore[attr-defined]


def test_assertionless_test_is_red(project: Project) -> None:
    """A test with no assertion cannot fail, so it proves nothing."""
    project.write(
        "tests/test_vacuous.py",
        '''
        def test_does_nothing() -> None:
            """Looks like a test. Cannot fail."""
            x = 1 + 1
            print(x)
        ''',
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "marker-no-assertion" in codes(result)


def test_asserting_test_passes(project: Project) -> None:
    """The proving path: a test that actually checks something."""
    project.write(
        "tests/test_real.py",
        """
        def test_adds() -> None:
            assert 1 + 1 == 2
        """,
    )
    assert project.run(_ID).verdict is Verdict.PASS


def test_pytest_raises_counts_as_an_assertion(project: Project) -> None:
    """`with pytest.raises(...)` is a real failure path, not an assertionless test."""
    project.write(
        "tests/test_raises.py",
        """
        import pytest


        def test_boom() -> None:
            with pytest.raises(ValueError):
                raise ValueError("expected")
        """,
    )
    assert project.run(_ID).verdict is Verdict.PASS


def test_xfail_without_reason_is_red(project: Project) -> None:
    """An xfail with no reason is undocumented debt nobody will revisit."""
    project.write(
        "tests/test_xfail.py",
        """
        import pytest


        @pytest.mark.xfail
        def test_known_broken() -> None:
            assert False
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "marker-xfail-no-reason" in codes(result)


def test_xfail_with_reason_passes(project: Project) -> None:
    project.write(
        "tests/test_xfail_ok.py",
        """
        import pytest


        @pytest.mark.xfail(reason="upstream bug #123, tracked")
        def test_known_broken() -> None:
            assert False
        """,
    )
    assert project.run(_ID).verdict is Verdict.PASS


def test_skipif_without_reason_is_red(project: Project) -> None:
    """A skip that names a condition but no reason hides why it does not run."""
    project.write(
        "tests/test_skipif.py",
        """
        import sys

        import pytest


        @pytest.mark.skipif(sys.platform == "win32")
        def test_unixy() -> None:
            assert True
        """,
    )
    result = project.run(_ID)
    assert result.verdict is Verdict.FAIL
    assert "marker-skipif-no-reason" in codes(result)


def test_no_tests_directory_skips(tmp_path_factory: pytest.TempPathFactory) -> None:
    """No tests dir means nothing to check — a skip, not a false pass."""
    from tests.conftest import Project as P

    root = tmp_path_factory.mktemp("notests")
    proj = P(root=root)
    proj.pyproject()
    result = proj.run(_ID)
    assert result.verdict is Verdict.SKIPPED
