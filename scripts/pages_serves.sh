#!/usr/bin/env bash
# Paces the Pages deploys and says whether the site serves this run's deploy yet.
#
#   scripts/pages_serves.sh pace             wait until PAGES_GAP_SECONDS have passed since the last Pages deploy
#   scripts/pages_serves.sh stamp <dir>      write <dir>/deploy.json for this run
#   scripts/pages_serves.sh deployed         record that this run deployed just now (for the next pace)
#   scripts/pages_serves.sh check <page_url>  wait until <page_url>deploy.json is this run's, or fail
#
# Pages accepts a deploy and reports it successful without serving it when a repository deploys too often: about
# ten deploys in the hour before, and most deploys stay unpublished. So every deploy waits for PAGES_GAP_SECONDS
# (default 330) after the one before it, this run's or an earlier run's (read from the Actions API, which needs
# `actions: read`; without it the wait is skipped with a warning). Run before the ingest, the wait also lets the
# releases that arrive meanwhile into the same deploy.
#
# A deploy that reports success is still only a report. So the deploy writes a stamp naming its run, and after
# deploying asks the live site for it, cache-busted, until the stamp is this run's or CHECK_SECONDS (default 240; a
# deploy normally shows within a minute) have passed.
# Run from the deploy job: GITHUB_RUN_ID, GITHUB_RUN_ATTEMPT and GITHUB_SHA name the run.
set -euo pipefail

stamp() {
  local dir="$1"
  mkdir -p "$dir"
  printf '{"run_id": %s, "run_attempt": %s, "sha": "%s", "built_at": "%s"}\n' \
    "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" "$GITHUB_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$dir/deploy.json"
}

# The newest finished Pages deploy of this repository, as epoch seconds; empty when none can be found.
last_deploy() {
  local mark="${RUNNER_TEMP:-/tmp}/pages-deployed-at" workflow runs id at
  if [[ -s "$mark" ]]; then
    cat "$mark"
    return 0
  fi
  # The Deploy runs one at a time (its concurrency group), so the newest earlier run that deployed holds the last
  # deploy. GITHUB_WORKFLOW_REF names the calling workflow, also when this job is a reusable workflow's.
  workflow="${GITHUB_WORKFLOW_REF%@*}"
  workflow="${workflow##*/}"
  runs=$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/${workflow}/runs?per_page=8" \
    --jq ".workflow_runs[] | select(.id != ${GITHUB_RUN_ID}) | .id") || return 0
  for id in $runs; do
    at=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${id}/jobs" --jq \
      '[.jobs[].steps[] | select(.name | startswith("Deploy to Pages")) | select(.conclusion == "success") | .completed_at] | max // empty') ||
      return 0
    if [[ -n "$at" ]]; then
      date -d "$at" +%s
      return 0
    fi
  done
}

pace() {
  local gap="${PAGES_GAP_SECONDS:-330}" last wait
  if ! last=$(last_deploy) || [[ -z "$last" ]]; then
    echo "::warning::Could not tell when Pages last deployed; deploying without waiting"
    return 0
  fi
  wait=$((last + gap - $(date +%s)))
  if ((wait <= 0)); then
    echo "The last Pages deploy was $(($(date +%s) - last)) s ago; no wait"
    return 0
  fi
  echo "The last Pages deploy was $(($(date +%s) - last)) s ago; waiting ${wait} s to keep ${gap} s between deploys"
  sleep "$wait"
}

deployed() {
  date +%s >"${RUNNER_TEMP:-/tmp}/pages-deployed-at"
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
  pace) pace ;;
  stamp) stamp "${2:?directory}" ;;
  deployed) deployed ;;
  check) check "${2:?page url}" ;;
  *)
    echo "usage: $0 pace | stamp <dir> | deployed | check <page_url>" >&2
    exit 2
    ;;
esac
