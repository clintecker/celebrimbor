"""The opinionated defaults `celebrimbor init` writes.

These are templates rather than generated config for a reason: an adopter has
to be able to read, edit and own them. A tool that writes config it then
treats as sacred has taken the project hostage, so everything here is plain
text the adopter is free to change — celebrimbor never re-reads these files to
check they still say what it wrote.

The rulesets are the ones celebrimbor holds *itself* to. Shipping a stricter
config than we pass would be the same failure as a blind verifier.
"""

from __future__ import annotations

RUFF = """
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = [
  "E", "W",    # pycodestyle
  "F",         # pyflakes
  "I",         # isort
  "N",         # pep8-naming
  "UP",        # pyupgrade
  "B",         # bugbear
  "A",         # builtins shadowing
  "C4",        # comprehensions
  "SIM",       # simplify
  "RET",       # return
  "ARG",       # unused arguments
  "PTH",       # use pathlib
  "C90",       # mccabe complexity
  "RUF",       # ruff-specific
]
ignore = [
  "E501",      # line length is the formatter's job, not the linter's
]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.per-file-ignores]
# Negative fixtures exist to be wrong. Linting them defeats their purpose.
"tests/negative/**" = ["ALL"]
"tests/known-bad/**" = ["ALL"]
""".lstrip()

MYPY = """
[tool.mypy]
python_version = "3.11"
strict = true
warn_unreachable = true

[[tool.mypy.overrides]]
module = ["tests.*"]
ignore_errors = true
""".lstrip()

PYTEST = """
[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
  "negative: a fixture that must turn a specific gate red",
  "slow: excluded from the fast stage",
]
# A warning that is not an error is a warning nobody reads.
filterwarnings = ["error"]
""".lstrip()

COVERAGE = """
[tool.coverage.run]
branch = true

[tool.coverage.report]
exclude_lines = ["pragma: no cover", "if TYPE_CHECKING:", "raise NotImplementedError"]
""".lstrip()

CELEBRIMBOR = """
[tool.celebrimbor]
source = "{source}"
tests = "tests"
""".lstrip()

PRE_COMMIT = """\
# Managed by `celebrimbor init`. One hook, on purpose.
#
# The ladder is not wired here tool-by-tool: `celebrimbor gate --fast` runs
# lint, format, types, known-bad and the surface audit in one process, in a
# deliberate order, with one consistent report. Listing each tool separately
# would mean two places to keep in sync and two different ideas of what
# "passing" means.
repos:
  - repo: local
    hooks:
      - id: celebrimbor-gate
        name: celebrimbor gate --fast
        entry: celebrimbor gate --fast
        language: system
        pass_filenames: false
        always_run: true
"""

KNOWN_BAD_README = """\
# known-bad

Every file in this directory is **deliberately wrong**, and something is
expected to say so.

This is the falsifier for the checkers themselves. A linter that has never been
observed to reject anything is a linter nobody should trust to reject the thing
that matters — so each file here names the checker that must catch it and the
diagnostic it must produce, in `expected.yaml`:

```yaml
unused_import.py:
  checker: ruff
  diagnostic: F401
  why: proves the unused-import rule is actually enabled
```

The gate checks this in both directions. A file with no entry is an orphan; an
entry naming a file that does not exist is a stale claim. Both are red — the
first because nobody knows what it is proving, the second because it is
proving nothing while looking like it is.

Being caught by *some* checker is not enough. The named checker must produce
the named diagnostic, because "something complained" is compatible with the
rule you care about having been silently disabled.
"""

KNOWN_BAD_EXPECTED = """\
# Each entry: which checker must reject this file, and with what diagnostic.
# Both directions are audited — orphan files and stale entries are red.
{}
"""

GITIGNORE_ADDITION = """
# celebrimbor
.celebrimbor/cache/
"""
