<!--
Thanks for contributing. Celebrimbor holds itself to its own gate; this
checklist is that gate, restated for a PR.
-->

## What this changes

<!-- A sentence or two. Link any issue it closes. -->

## Checklist

- [ ] `celebrimbor gate --full` is green.
- [ ] `python -m pytest` passes.
- [ ] If this adds or changes a gate: it names a `falsified_by`, and there is a
      **negative fixture** in `tests/negative/` that the gate turns red.
- [ ] Comments explain *why* where a subtler option was rejected.
- [ ] `CHANGELOG.md` updated if this is user-visible.
