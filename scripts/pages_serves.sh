#!/usr/bin/env bash
# Says whether the Pages site serves this run's deploy yet.
#
#   scripts/pages_serves.sh stamp <dir>      write <dir>/deploy.json for this run
#   scripts/pages_serves.sh check <page_url>  wait until <page_url>deploy.json is this run's, or fail
#
# deploy-pages reports success when GitHub has accepted a deployment, not when the site serves it. On 2026-11-04 five
# deploys in a row (18:37 to 19:44 UTC) reported success while the hub kept serving its 18:32 deploy, with GitHub's
# status page all green; three releases waited over an hour for their pages and every party thought its part was
# done. The cause, found on 2026-11-05: deploy-pages names a deploy after the commit, and Pages answers a second
# deploy of the same commit with the first one's status. The Deploy now uses workflows' deploy-pages, which gives each
# deploy a version of its own, and keeps this check, because a success Pages reports is still only a report. So the
# deploy writes a stamp naming its run, and after deploying asks the live site for it, cache-busted, until the stamp
# is this run's or CHECK_SECONDS (default 240; a deploy normally shows within a minute) have passed.
# Run from the deploy job: GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT and GITHUB_SHA name the run.
set -euo pipefail

stamp() {
  local dir="$1"
  mkdir -p "$dir"
  printf '{"run_id": %s, "run_attempt": %s, "sha": "%s", "built_at": "%s"}\n' \
    "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" "$GITHUB_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$dir/deploy.json"
}

check() {
  local url="${1%/}/deploy.json" limit="${CHECK_SECONDS:-240}" every="${CHECK_EVERY:-10}"
  local start=$SECONDS tries=0 body served=""
  while :; do
    tries=$((tries + 1))
    body=$(curl -fsS --max-time 15 -H 'Cache-Control: no-cache' "${url}?run=${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-${tries}" 2>/dev/null || true)
    served=$(jq -r '"\(.run_id)-\(.run_attempt)"' <<<"$body" 2>/dev/null || true)
    if [[ "$served" == "${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" ]]; then
      echo "Pages serves this deploy (after $((SECONDS - start)) s)"
      return 0
    fi
    if ((SECONDS - start >= limit)); then
      echo "::warning::Pages reported the deploy successful but after ${limit} s still serves ${served:-nothing readable} at ${url}, not run ${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
      return 1
    fi
    sleep "$every"
  done
}

case "${1:-}" in
  stamp) stamp "${2:?directory}" ;;
  check) check "${2:?page url}" ;;
  *)
    echo "usage: $0 stamp <dir> | check <page_url>" >&2
    exit 2
    ;;
esac
