#!/usr/bin/env bash
# Fetches the hub's data into data/ for local work.
#
#   scripts/data.sh
#
# The data lives on the `data` branch as one commit with no history (scripts/commit_data.sh), so this is a depth-1
# clone of that branch, and every later run fetches only what changed. It discards local changes in data/: CI owns
# the data, and the ingest commands can always rebuild what a local run wrote.
set -euo pipefail

cd "$(dirname "$0")/.."
if [ -d data/.git ]; then
  git -C data fetch --quiet --depth 1 origin data
  git -C data reset --quiet --hard FETCH_HEAD
  git -C data clean -fdq
elif [ -e data ] && [ -n "$(ls -A data)" ]; then
  echo "data/ exists but is not a checkout of the data branch; move it aside and run this again" >&2
  exit 1
else
  rmdir data 2>/dev/null || true
  git clone --quiet --depth 1 --branch data --single-branch "$(git remote get-url origin)" data
fi
echo "data/ at $(git -C data log -1 --format='%h, %cr')"
