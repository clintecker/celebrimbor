#!/usr/bin/env bash
#
# Refuse to commit onto a detached HEAD.
#
# A commit made off-branch is invisible to `git push origin main` — which reports
# "Everything up-to-date" while doing nothing — and is exactly how a release's
# tag checkout (`gh release create` checks out the tag) silently swallows later
# work. This is a structural guard, not a reminder: the mistake is made
# impossible, rather than the human being trusted to notice it. No amount of
# `celebrimbor gate --fast` would catch it, because the commit itself is fine —
# it is *where* the commit lands that is wrong.
set -euo pipefail

if git symbolic-ref -q HEAD >/dev/null 2>&1; then
    exit 0
fi

echo "refusing to commit: HEAD is detached — you are not on a branch." >&2
echo "  You are probably parked on a tag after cutting a release." >&2
echo "  Your changes are safe; get back on main first, then commit:" >&2
echo "      git checkout main" >&2
exit 1
