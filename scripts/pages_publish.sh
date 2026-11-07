#!/usr/bin/env bash
# Publishes a built site to the `gh-pages` branch, which GitHub Pages serves, and checks that Pages serves it.
#
#   scripts/pages_publish.sh stamp <dir>     write <dir>/deploy.json for this run and <dir>/.nojekyll
#   scripts/pages_publish.sh publish <dir>   make <dir> the one commit of gh-pages, unless it holds the same files
#   scripts/pages_publish.sh check           wait until Pages serves the deploy.json of gh-pages, or fail
#
# gh-pages holds one commit, as the data branch does: every publish replaces it with a new root commit pushed with a
# lease, so the branch's history never grows. The previous commit is fetched first, so a push sends only the files
# that changed. When the build is the same as what gh-pages holds (deploy.json's `content`, a digest of every other
# file), nothing is pushed and Pages does not build; Pages is only asked to build gh-pages again when the site does
# not serve it. Control dispatches the Deploy at most nine times an hour (its deploys.py), below Pages' ten builds an
# hour for a site published from a branch.
#
# A Pages build that reports success is still only a report. So deploy.json names the run that pushed, and `check`
# asks the live site for it, cache-busted, until it is gh-pages' or CHECK_SECONDS (default 300) have passed.
#
# Run from the Deploy job with GH_TOKEN (contents: write, pages: write); GITHUB_REPOSITORY, GITHUB_RUN_ID,
# GITHUB_RUN_ATTEMPT and GITHUB_SHA name the repository and the run, and GITHUB_OUTPUT gets `pushed` and `sha`.
set -euo pipefail

branch=gh-pages
remote="https://github.com/${GITHUB_REPOSITORY}.git"
git_dir="${RUNNER_TEMP:-/tmp}/gh-pages.git"
state="${RUNNER_TEMP:-/tmp}/gh-pages.sha"

# The digest of every file of <dir> but deploy.json: names and contents.
content() {
  (cd "$1" && find . -type f ! -path ./deploy.json -print0 | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -c1-64)
}

stamp() {
  local dir="$1"
  mkdir -p "$dir"
  : >"$dir/.nojekyll" # serve the files as built: Jekyll would drop every path starting with _ (Astro's _astro/)
  jq -n --argjson run_id "$GITHUB_RUN_ID" --argjson run_attempt "$GITHUB_RUN_ATTEMPT" --arg sha "$GITHUB_SHA" \
    --arg built_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg content "$(content "$dir")" \
    '{run_id: $run_id, run_attempt: $run_attempt, sha: $sha, built_at: $built_at, content: $content}' >"$dir/deploy.json"
}

g() {
  git --git-dir="$git_dir" -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $(printf 'x-access-token:%s' "$GH_TOKEN" | base64 -w0)" "$@"
}

output() {
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then echo "$1=$2" >>"$GITHUB_OUTPUT"; fi
}

# The newest Pages build: "<commit> <status>", or nothing.
latest_build() {
  gh api "repos/${GITHUB_REPOSITORY}/pages/builds/latest" --jq '"\(.commit) \(.status)"' 2>/dev/null || true
}

# Waits until Pages has built <sha>, asking for a build when none starts on its own within a minute.
built() {
  local sha="$1" start=$SECONDS asked=0 latest
  while :; do
    latest=$(latest_build)
    if [[ "${latest%% *}" == "$sha" ]]; then
      case "${latest#* }" in
        built)
          echo "Pages built ${sha:0:7} (after $((SECONDS - start)) s)"
          return 0
          ;;
        errored)
          echo "::error::the Pages build of ${sha:0:7} errored"
          return 1
          ;;
      esac
    elif ((!asked && SECONDS - start >= 60)); then
      echo "No Pages build of ${sha:0:7} started; asking for one"
      gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" --silent
      asked=1
    fi
    if ((SECONDS - start >= ${BUILD_SECONDS:-600})); then
      echo "::error::Pages did not build ${sha:0:7} within ${BUILD_SECONDS:-600} s (newest build: ${latest:-none})"
      return 1
    fi
    sleep 10
  done
}

# The run_id of the deploy.json the site serves now, cache-busted.
served() {
  local url tries="${1:-0}"
  url="$(gh api "repos/${GITHUB_REPOSITORY}/pages" --jq .html_url)"
  curl -fsS --max-time 15 -H 'Cache-Control: no-cache' "${url%/}/deploy.json?run=${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}-${tries}" 2>/dev/null |
    jq -r '.run_id // empty' 2>/dev/null || true
}

publish() {
  local dir="$1" old="" before="" ours tree commit
  rm -rf "$git_dir"
  git init --quiet --bare "$git_dir"
  if g ls-remote --exit-code "$remote" "refs/heads/$branch" >/dev/null; then
    g fetch --quiet --depth 1 "$remote" "refs/heads/$branch"
    old=$(g rev-parse FETCH_HEAD)
    before=$(g show "$old:deploy.json" 2>/dev/null | jq -r '.content // empty' 2>/dev/null || true)
  fi
  ours=$(jq -r .content "$dir/deploy.json")
  if [[ -n "$old" && "$before" == "$ours" ]]; then
    echo "gh-pages already holds this build (${old:0:7}); nothing to push"
    echo "$old" >"$state"
    output pushed false
    output sha "$old"
    if [[ "$(served)" == "$(g show "$old:deploy.json" | jq -r .run_id)" ]]; then
      echo "Pages serves it"
      return 0
    fi
    echo "Pages does not serve gh-pages; asking for a build"
    gh api -X POST "repos/${GITHUB_REPOSITORY}/pages/builds" --silent
    sleep 5
    built "$old"
    return
  fi
  export GIT_INDEX_FILE="${RUNNER_TEMP:-/tmp}/gh-pages.index"
  rm -f "$GIT_INDEX_FILE"
  g --work-tree="$dir" add --all .
  tree=$(g write-tree)
  commit=$(GIT_AUTHOR_NAME="github-actions[bot]" GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com" \
    GIT_COMMITTER_NAME="github-actions[bot]" GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com" \
    g commit-tree "$tree" -m "Publish run ${GITHUB_RUN_ID}")
  # The Deploy runs one at a time (its concurrency group), so a lost lease means someone pushed by hand: fail.
  g push --quiet --force-with-lease="refs/heads/$branch:$old" "$remote" "$commit:refs/heads/$branch"
  echo "Pushed ${commit:0:7} to gh-pages (replacing ${old:0:7})"
  echo "$commit" >"$state"
  output pushed true
  output sha "$commit"
  built "$commit"
}

check() {
  local sha want start=$SECONDS tries=0 now=""
  sha=$(cat "$state")
  want=$(g show "$sha:deploy.json" | jq -r .run_id)
  while :; do
    tries=$((tries + 1))
    now=$(served "$tries")
    if [[ "$now" == "$want" ]]; then
      echo "Pages serves gh-pages ${sha:0:7}, run ${want} (after $((SECONDS - start)) s)"
      return 0
    fi
    if ((SECONDS - start >= ${CHECK_SECONDS:-300})); then
      echo "::error::Pages built gh-pages ${sha:0:7} but after ${CHECK_SECONDS:-300} s still serves run ${now:-nothing readable}, not run ${want}"
      return 1
    fi
    sleep 10
  done
}

case "${1:-}" in
  stamp) stamp "${2:?directory}" ;;
  publish) publish "${2:?directory}" ;;
  check) check ;;
  *)
    echo "usage: $0 stamp <dir> | publish <dir> | check" >&2
    exit 2
    ;;
esac
