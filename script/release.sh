#!/usr/bin/env bash
# Set the version in pyproject.toml, the integration manifest (and uv.lock when
# it is tracked), commit it as chore(release), and create the matching
# annotated git tag. Nothing is pushed.
#
# Usage: release.sh <auto|major|minor|patch|X.Y.Z>
#
# auto picks the bump from the Conventional Commits since the last tag: a
# breaking change is major (minor before 1.0.0), a feat is minor, anything
# else is patch.
#
# Home Assistant reads the version from custom_components/fglair_local/manifest.json
# and HACS offers an update when a new tag is released, so the files have to
# agree with the tag. The Release workflow refuses a tag that does not.
set -euo pipefail

usage="usage: release.sh <auto|major|minor|patch|X.Y.Z>"
bump="${1:?$usage}"

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="custom_components/fglair_local/manifest.json"
cd "$repo"

if [ -n "$(git status --porcelain)" ]; then
  echo "working tree not clean, commit or stash changes first" >&2
  exit 1
fi

branch="$(git symbolic-ref --quiet --short HEAD || true)"
if [ "$branch" != main ]; then
  echo "releases are cut from main, currently on ${branch:-a detached HEAD}" >&2
  exit 1
fi

# Unpushed local commits are fine, they go out with the tag.
git fetch --quiet --tags origin main
behind="$(git rev-list --count HEAD..origin/main)"
if [ "$behind" -gt 0 ]; then
  echo "main is ${behind} commit(s) behind origin/main, pull first" >&2
  exit 1
fi

if [ "$bump" = auto ]; then
  if ! last="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null)"; then
    echo "no previous release tag, pass the version explicitly" >&2
    exit 1
  fi
  range="${last}..HEAD"
  if [ -z "$(git rev-list "$range")" ]; then
    echo "no commits since ${last}, nothing to release" >&2
    exit 1
  fi
  # git log --grep matches per line, so a footer is found anywhere in the body.
  breaking="$(git log -E --format='  %h %s' --grep='^[[:alnum:]]+(\([^)]*\))?!:' --grep='^BREAKING[ -]CHANGE:' "$range")"
  features="$(git log -E --format='  %h %s' --grep='^feat(\([^)]*\))?:' "$range")"
  if [ -n "$breaking" ]; then
    current="$(uv version --short)"
    if [ "${current%%.*}" = 0 ]; then
      bump=minor
    else
      bump=major
    fi
    echo "auto: ${bump}, breaking changes since ${last}:"
    echo "$breaking"
  elif [ -n "$features" ]; then
    bump=minor
    echo "auto: minor, features since ${last}:"
    echo "$features"
  else
    bump=patch
    echo "auto: patch, no features or breaking changes since ${last}"
  fi
fi

files=(pyproject.toml "$manifest")
uv_args=()
if git ls-files --error-unmatch uv.lock >/dev/null 2>&1; then
  files+=(uv.lock)
else
  # Without a tracked lockfile, do not create one as a side effect.
  uv_args+=(--frozen)
fi

case "$bump" in
  major | minor | patch) uv version "${uv_args[@]}" --bump "$bump" ;;
  [0-9]*.[0-9]*.[0-9]*) uv version "${uv_args[@]}" "$bump" ;;
  *)
    echo "$usage" >&2
    exit 1
    ;;
esac

version="$(uv version --short)"
tag="v${version}"

if git rev-parse -q --verify "refs/tags/${tag}" >/dev/null; then
  git checkout -- "${files[@]}"
  echo "tag ${tag} already exists" >&2
  exit 1
fi

python3 - "$manifest" "$version" <<'PY'
import pathlib
import re
import sys

path, version = pathlib.Path(sys.argv[1]), sys.argv[2]
text = path.read_text()
patched, count = re.subn(r'"version": "[^"]*"', f'"version": "{version}"', text)
if count != 1:
    sys.exit(f"expected one version key in {path}, found {count}")
path.write_text(patched)
PY

# An explicit version that is already the current one leaves nothing to commit,
# which is how an existing version gets its first tag.
if [ -n "$(git status --porcelain -- "${files[@]}")" ]; then
  git add -- "${files[@]}"
  git commit -m "chore(release): ${tag}"
fi

git tag -a "${tag}" -m "${tag}"

echo "version ${version}, tagged ${tag}"
echo "run the 'Release: Push Tags to Origin' task (or 'git push --follow-tags origin main') to publish"
echo "CI verifies the tag against both versions, lints, tests, runs hassfest, then creates the GitHub release"
