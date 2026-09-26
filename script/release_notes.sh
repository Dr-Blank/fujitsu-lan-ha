#!/usr/bin/env bash
# Print Markdown release notes for a tag, grouping the commits since the
# previous tag by their Conventional Commits type.
#
# Usage: release_notes.sh <tag>
#
# The release workflow passes the output to `gh release create --notes-file`,
# which prepends it to GitHub's generated notes (pull requests, contributors,
# full changelog link).
set -euo pipefail

tag="${1:?usage: release_notes.sh <tag>}"

if previous="$(git describe --tags --abbrev=0 --match 'v*' "${tag}^" 2>/dev/null)"; then
  range="${previous}..${tag}"
else
  previous=""
  range="${tag}"
fi

declare -A sections=()
breaking=""

while IFS=$'\t' read -r sha subject; do
  [ -n "$sha" ] || continue
  short="${sha:0:7}"
  if [[ "$subject" =~ ^([a-z]+)(\(([^\)]+)\))?(!)?:[[:space:]]+(.+)$ ]]; then
    type="${BASH_REMATCH[1]}"
    scope="${BASH_REMATCH[3]}"
    bang="${BASH_REMATCH[4]}"
    description="${BASH_REMATCH[5]}"
  else
    type="other"
    scope=""
    bang=""
    description="$subject"
  fi

  # The version bump commit carries no change of its own.
  if [ "$type" = "chore" ] && [ "$scope" = "release" ]; then
    continue
  fi

  line="- ${scope:+**${scope}:** }${description} (${short})"
  if [ -n "$bang" ] || grep -q '^BREAKING[ -]CHANGE:' <<<"$(git log -1 --format=%B "$sha")"; then
    breaking+="${line}"$'\n'
  fi

  case "$type" in
    feat) key="feat" ;;
    fix) key="fix" ;;
    perf) key="perf" ;;
    refactor) key="refactor" ;;
    docs) key="docs" ;;
    build | ci | chore | style | test) key="maintenance" ;;
    *) key="other" ;;
  esac
  sections[$key]+="${line}"$'\n'
done < <(git log --no-merges --format='%H%x09%s' "$range")

print_section() {
  local title="$1" body="$2"
  if [ -n "$body" ]; then
    printf '### %s\n\n%s\n' "$title" "$body"
  fi
}

if [ -n "${previous:-}" ]; then
  printf '## Commits since %s\n\n' "$previous"
else
  printf '## Commits\n\n'
fi
if [ ${#sections[@]} -eq 0 ]; then
  printf 'No changes besides the version bump.\n'
fi
print_section "Breaking changes" "$breaking"
print_section "Features" "${sections[feat]:-}"
print_section "Fixes" "${sections[fix]:-}"
print_section "Performance" "${sections[perf]:-}"
print_section "Refactoring" "${sections[refactor]:-}"
print_section "Documentation" "${sections[docs]:-}"
print_section "Maintenance" "${sections[maintenance]:-}"
print_section "Other changes" "${sections[other]:-}"
