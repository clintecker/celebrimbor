#!/usr/bin/env bash
#
# Cut a release without the gh detached-HEAD footgun.
#
#   gh release create <new-tag> creates the tag and then *checks it out*,
#   silently detaching HEAD from main. The next commit then lands off-branch and
#   `git push origin main` reports "up-to-date" while doing nothing. This script
#   avoids it by creating and pushing the tag itself, then calling gh with
#   --verify-tag, so gh finds the tag already present, creates nothing, and never
#   checks anything out. HEAD stays on main.
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

# -- prove nothing detached -------------------------------------------------
echo
echo "released $tag"
echo "  branch:      $(git branch --show-current || echo 'DETACHED — unexpected!')"
echo "  HEAD:        $(git rev-parse --short HEAD)"
echo "  origin/main: $(git rev-parse --short origin/main)"
echo "  tag $tag: $(git rev-list -n1 "$tag" | cut -c1-7)"
