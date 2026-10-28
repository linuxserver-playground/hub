#!/usr/bin/env bash
# Publishes data/ as the one commit of the `data` branch.
#
#   scripts/commit_data.sh
#
# data/ is a depth-1 checkout of `data`, a branch that only ever holds one commit: every change replaces it with a new
# root commit, so the data's history never grows (the replaced commit becomes unreachable and GitHub collects it). The
# code on main keeps its own history, free of data commits.
#
# deploy.yml and refresh.yml both write data/ and may push at the same moment. When the other one replaced the commit
# first, the lease fails; this one then merges its own changes onto theirs, three-way against the commit it checked
# out, and pushes again. They write different files (lsio_hub/store.py), so the merge is clean; should they ever
# change the same file, the merge conflicts, and a conflict fails the run rather than dropping either side (the next
# run redoes it).
#
# With no history there is no revert, and the data is not all rebuildable (history.json keeps every release, the
# reconcile reads the newest 30). So the first publish of each UTC day is kept as refs/data-history/<date> for a
# week (roll back by force-pushing one to refs/heads/data), and a publish that would drop more than a tenth of the
# files, the mark of a glitched run, is refused unless ALLOW_SHRINK=1.
#
# The count leaves out the retired per-architecture scan files (images/*/builds/<tag>.vulns.<arch>.json, about a fifth
# of the files when they were retired): the ingest replaces each build's pair with one file of counts once
# (lsio_hub/ingest.py, migrate_vulns), an intended drop the guard must not refuse. Once none are left this changes
# nothing, and the pattern can go.
set -euo pipefail

branch=data
cd "$(dirname "$0")/../data"

files() { git ls-tree -r --name-only "$1" | grep -cvE '^images/[^/]+/builds/.+\.vulns\.(amd64|arm64)\.json$' || true; }

# Refuses to replace $1 with $2 when that drops more than a tenth of the files.
guard() {
  local before after
  before=$(files "$1")
  after=$(files "$2")
  if [ "${ALLOW_SHRINK:-}" != 1 ] && [ $((after * 10)) -lt $((before * 9)) ]; then
    echo "::error::data: refusing to publish $after files over $before (ALLOW_SHRINK=1 if that is intended)"
    exit 1
  fi
}

# Keeps $1 as today's refs/data-history/<date> unless today already has one, and drops those older than a week.
keep() {
  local day cutoff ref
  day=$(date -u +%F)
  cutoff=$(date -u -d '7 days ago' +%F)
  git ls-remote --exit-code origin "refs/data-history/$day" >/dev/null && return
  git push --quiet origin "$1:refs/data-history/$day"
  git ls-remote origin 'refs/data-history/*' | while read -r _ ref; do
    if [[ "${ref##*/}" < "$cutoff" ]]; then git push --quiet origin ":$ref"; fi
  done
}

git add -A
if git diff --cached --quiet; then
  echo "data: nothing changed"
  exit 0
fi

base=$(git rev-parse HEAD)
ours=$(git commit-tree "$(git write-tree)" -m "Update data")
for attempt in 1 2 3 4 5; do
  guard "$base" "$ours"
  if git push --force-with-lease="$branch:$base" origin "$ours:refs/heads/$branch"; then
    # The merged tree when a retry merged, so the steps after this one read what was published.
    git reset --quiet --hard "$ours"
    keep "$ours" || echo "::warning::data: could not keep today's copy in refs/data-history/"
    exit 0
  fi
  if [ "$attempt" = 5 ]; then
    echo "::error::data: the branch kept moving; gave up after 5 attempts"
    exit 1
  fi
  sleep $((attempt * 3))
  git fetch --quiet --depth 1 origin "$branch"
  theirs=$(git rev-parse FETCH_HEAD)
  if ! merged=$(git merge-tree --write-tree --merge-base="$base" "$ours" "$theirs"); then
    echo "::error::data: another writer changed the same files"
    echo "$merged"
    exit 1
  fi
  base=$theirs
  ours=$(git commit-tree "${merged%%$'\n'*}" -m "Update data")
done
