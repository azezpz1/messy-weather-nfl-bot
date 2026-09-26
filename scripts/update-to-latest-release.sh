#!/usr/bin/env bash
# Updates the local checkout to the latest published GitHub release tag,
# then re-syncs dependencies. Intended to be run from the repo root (e.g. as
# the first line of the wrapper script your crontab invokes) so a scheduled
# job always runs the latest release instead of tracking `main` directly.
#
# See the "Updating to the latest release" section of the README for
# details on why this checks the latest *published release* rather than the
# newest tag.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! command -v git >/dev/null 2>&1; then
  echo "error: git is required" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl is required" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv is required (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

remote_url=$(git remote get-url origin)
repo=$(echo "$remote_url" | sed -E 's#^.*[:/]([^/]+/[^/]+)$#\1#; s#\.git$##')

echo "Checking latest release for $repo..."

api_url="https://api.github.com/repos/$repo/releases/latest"

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  # Pass the token via a curl config read from stdin rather than -H/argv, so
  # it doesn't show up in `ps` output for other local users to see.
  release_json=$(curl -fsSL --config - <<EOF
url = "$api_url"
header = "Authorization: Bearer ${GITHUB_TOKEN//\"/\\\"}"
EOF
)
else
  release_json=$(curl -fsSL "$api_url")
fi

latest_tag=$(echo "$release_json" | grep -m1 '"tag_name"' | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')

if [[ -z "$latest_tag" ]]; then
  echo "error: could not determine latest release tag for $repo" >&2
  echo "$release_json" >&2
  exit 1
fi

echo "Latest published release: $latest_tag"

git fetch --tags

current_tag=$(git describe --tags --exact-match 2>/dev/null || true)
if [[ "$current_tag" == "$latest_tag" ]]; then
  echo "Already on $latest_tag, nothing to do."
else
  git checkout "$latest_tag"
  echo "Checked out $latest_tag"
fi

uv sync
