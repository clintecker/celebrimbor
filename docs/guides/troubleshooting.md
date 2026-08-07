# Troubleshooting

Every red or skipped line celebrimbor prints is trying to tell you something
specific. This page decodes the ones people hit most often. And because the tool
*fails closed* — when it can't prove something is right, it stops and refuses
rather than waving it through — several of these are red *on purpose*.

## The four verdicts, and which are red

| Verdict | Red? | Meaning |
|---|:--:|---|
| `✓ pass` | no | checked and held |
| `– skipped` | no | not applicable — carries a reason |
| `✗ fail` | **yes** | checked and violated — carries a finding |
| `⊘ refused` | **yes** | could **not** be checked |

The one people trip on: **`⊘ refused` is red.** "I couldn't check this" is not the
same as "this is fine" — treating them the same is exactly how a missing tool or a
file that won't parse turns into a silent pass. See
[Fail closed](../concepts/fail-closed.md).

## Common messages

**`⊘ … the check itself raised`** — a check threw an exception. The traceback is
in the reason (`-v` shows it). This is a bug in the *check*, not your code — and
if it's a custom check, it should return `CheckResult.refused(...)` with a reason
instead of raising.

**`– skipped: no surface map — run celebrimbor init --surfaces`** — one of the
proving checks has nothing to read yet, because there's no surface map (the list
of your public functions and the job assigned to each). This is **not red**:
those checks are opt-in. Run `celebrimbor init --surfaces`, then `celebrimbor
ratify`. Until you do, only the everyday checks run.

**`✗ … is ratified but its shape has drifted`** — you confirmed this function's
job by hand (you *ratified* it), and that confirmation is *pinned* to the code as
it was then. Since then the function has changed character — it now reaches for
something in the outside world, or can fail where it couldn't, or alters its
inputs — so the
[pin](../concepts/roles.md#ratification-is-pinned-to-the-code) no longer matches.
Check that the role still fits, then re-run `celebrimbor ratify <module>`. This is
the gate catching an edit that outgrew its sign-off.

**`✗ … 3 new or worsened structural breach(es)`** — you added complexity past the
budget *or* past the grandfathered starting line. Fix the code, or — if you're
adopting on a legacy tree — record the existing debt once as that starting line:
`celebrimbor gate --update-baselines --reason "adopting"` in CI. See
[Ratchets](../gate/ratchets.md#structure-grandfather-the-debt-hold-the-line).

**`⊘ coverage could not be measured` / `– no baseline yet`** — the coverage
ratchet (the one-way gate that lets coverage rise but not quietly fall) reads a
`.coverage` file, so run your suite under `coverage run -m pytest` first. On a dev
box with no committed starting line it *skips* — starting lines are only ever set
in CI, so a local run never holds you to a floor higher than CI will. See
[Ratchets](../gate/ratchets.md).

**`⊘ the set of changed files could not be determined`** — the
[impact gate](../gate/ledgers.md#the-impact-gate) (which flags changes to
important code no recorded promise is watching over) needs something to compare
against. In a PR it works this out automatically from the merge base; locally,
give it one with `--diff-base HEAD` (or `--diff-base main`). It refuses rather
than assume nothing changed.

**`✗ unproven … past its review date` / `pending … passed its review date`** —
a dated admission of missing proof ([`Unproven`](../gate/meta.md) or a `pending`
producer) has run out its clock. Write the missing falsifier or verifier, or
re-justify it with a new date. The list of allowed exceptions is meant to shrink,
never grow.

**`⊘ … config key 'foo' is not recognized`** — celebrimbor refuses an unknown
`[tool.celebrimbor]` key rather than ignoring it; a mistyped key would silently
leave a setting unenforced. Fix the spelling — the
[configuration reference](../reference/configuration.md) lists every valid key.

## "It's red and I think it's wrong"

celebrimbor's own gate is green at every stage, so a genuine false positive is a
bug worth reporting. But first: run with `-v` to see the full finding and hint,
and ask whether the fix it's pointing at is the honest one. This is the
Celebrimbor lesson in miniature — the flaw you can't see is the dangerous one. The
most common "false positive" is a `pure` function that really did quietly pick up
a side effect, or a `verifier` that really can't fail. If it's genuinely wrong,
[open an issue](https://github.com/clintecker/celebrimbor/issues).
