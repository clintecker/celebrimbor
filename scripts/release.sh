#!/usr/bin/env bash
#
# Cut a release without the gh detached-HEAD footgun.
#
#   gh release create <new-tag> creates the tag and then *checks it out*,
#   silently detaching HEAD from main. The next commit then lands off-branch and
#   `git push origin main` reports "up-to-date" while doing nothing. This script
#   creates and pushes the tag itself, then calls gh with --verify-tag so gh finds
#   the tag already present and creates nothing — but gh has still been observed to
#   detach HEAD anyway, so we do NOT trust it: an EXIT trap restores main and the
#   script fails loudly if it cannot. Belt and suspenders, because a "proof" that
#   reads HEAD at one instant cannot catch a detach that happens after it.
#
# Flow (do the creative parts first, by hand):
#   1. bump the version in pyproject.toml + src/celebrimbor/__init__.py
#   2. add the CHANGELOG.md entry  (its body becomes the GitHub release notes)
#   3. commit and `git push origin main`
#   4. scripts/release.sh v0.11.0
#
set -euo pipefail

tag="${1:?usage: scripts/release.sh vX.Y.Z}"
[[ "$tag" == v?*.?*.?* ]] || { echo "error: tag must look like vX.Y.Z (got '$tag')"; exit 1; }
version="${tag#v}"

die() { echo "error: $*" >&2; exit 1; }

# -- guards: release only from a clean, pushed main --------------------------
branch="$(git branch --show-current)"
[[ "$branch" == "main" ]] || die "not on main (on '${branch:-DETACHED HEAD}'); run: git checkout main"
[[ -z "$(git status --porcelain)" ]] || die "working tree is not clean; commit or stash first"
git fetch origin main --quiet
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] \
    || die "main and origin/main differ; push your release commit first"

# gh has been observed to leave HEAD detached at the tag despite --verify-tag, so
# we refuse to trust it. Restore main on exit and fail loudly if we cannot. Armed
# only now that the guards above have confirmed we started on a clean, synced main.
_restore_main() {
    local rc=$?
    if ! git symbolic-ref -q HEAD >/dev/null 2>&1; then
        echo "note: gh left HEAD detached at the tag; restoring main" >&2
        git checkout --quiet main || true
    fi
    if [[ "$(git branch --show-current)" != "main" ]]; then
        echo "error: release ended off 'main' and could not restore it." >&2
        echo "       do NOT commit until you are back on main: git checkout main" >&2
        exit 1
    fi
    [[ "$rc" -eq 0 ]] && echo "HEAD verified on main at $(git rev-parse --short HEAD)"
    return "$rc"
}
trap _restore_main EXIT

# -- guards: the version and changelog must actually be there ---------------
grep -q "version = \"$version\"" pyproject.toml || die "pyproject.toml is not at version $version"
grep -q "__version__ = \"$version\"" src/celebrimbor/__init__.py || die "__version__ is not $version"
git rev-parse -q --verify "refs/tags/$tag" >/dev/null && die "tag $tag already exists"

notes="$(awk -v v="$version" '$0 ~ "^## " v " " {f=1; next} /^## / {f=0} f' CHANGELOG.md)"
[[ -n "${notes//[[:space:]]/}" ]] || die "no CHANGELOG.md entry for $version"

# -- build, tag, push the tag, then create the release against it ------------
rm -rf dist && uv build

git tag -a "$tag" -m "release $tag"
git push origin "$tag"
printf '%s\n' "$notes" | gh release create "$tag" dist/* --verify-tag --title "$tag" --notes-file -

# The EXIT trap re-asserts main and prints the verified HEAD as the final word —
# it catches a detach that happens anywhere above, which a one-shot echo cannot.
echo
echo "released $tag (origin/main $(git rev-parse --short origin/main), tag $(git rev-list -n1 "$tag" | cut -c1-7))"
