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
