#!/usr/bin/env bash
# Pushes a generated store to its own repository, because Umbrel and Runtipi clone a git repository and want the
# store's files at its root. Idempotent: the target's contents are replaced by the source directory plus a
# generated README, and a commit is made only when that changes anything.
#
#   STORE_TOKEN=<installation token> scripts/publish_store.sh <platform> <source dir> <owner/repo> [branch]
#   STORE_CLONE_URL=/path/to/bare.git STORE_TOKEN=x scripts/publish_store.sh umbrel out/stores/umbrel o/r   # local
#
# <platform> is umbrel or runtipi (chooses the README text), <source dir> is out/stores/<platform>/, [branch] is
# the target's default branch (main; created when the repository is empty). The push is retried once after a
# fetch and rebase, the generated snapshot winning any conflict.
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: STORE_TOKEN=... $0 <platform> <source dir> <owner/repo> [branch]" >&2
  exit 2
fi
platform=$1
source_dir=$(realpath "$2")
repo=$3
branch=${4:-main}
: "${STORE_TOKEN:?STORE_TOKEN must hold a token with contents: write on $repo}"
hub_repo=${GITHUB_REPOSITORY:-linuxserver-playground/hub}
hub_url="https://github.com/${hub_repo}"
repo_url="https://github.com/${repo}"

if [ ! -d "$source_dir" ]; then
  echo "no generated output at $source_dir" >&2
  exit 1
fi

case "$platform" in
  unraid)
    title="LinuxServer.io Unraid templates"
    how_to="Community Applications lists template repositories once its moderators have added them. Until this one is, copy an image's XML into \`/boot/config/plugins/dockerMan/templates-user/\` on the flash drive and pick it under *Docker*, *Add Container*, *Template*. Each template's \`TemplateURL\` points back here, so Unraid picks up changes."
    layout="One \`<image>.xml\` per image at the root, deprecated images in \`deprecated/\`, and \`ignore.list\` for images that opt out of Unraid."
    ;;
  umbrel)
    title="LinuxServer.io Umbrel community app store"
    how_to="In umbrelOS open the App Store, choose *Community App Stores* and add \`${repo_url}\`."
    layout="\`umbrel-app-store.yml\` (store id \`lsio\`) and one \`lsio-<app>/\` directory per image with \`umbrel-app.yml\` and \`docker-compose.yml\`."
    ;;
  runtipi)
    title="LinuxServer.io Runtipi app store"
    how_to="In Runtipi open *Settings*, choose *App Stores*, *Add App Store*, and paste \`${repo_url}\`."
    layout="\`apps/<app>/\` per image with \`config.json\`, \`docker-compose.yml\` (dynamic compose, \`x-runtipi\` schema 2) and \`metadata/description.md\`."
    ;;
  *)
    echo "unknown platform $platform (unraid, umbrel or runtipi)" >&2
    exit 2
    ;;
esac

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
# STORE_CLONE_URL overrides the remote for local runs against a bare repository.
clone_url=${STORE_CLONE_URL:-"https://x-access-token:${STORE_TOKEN}@github.com/${repo}.git"}

git clone --quiet "$clone_url" "$work/repo"
cd "$work/repo"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
if git rev-parse --verify --quiet "origin/$branch" >/dev/null; then
  git checkout --quiet "$branch"
else
  # An empty repository: the first push creates the branch.
  git checkout --quiet --orphan "$branch"
fi

# Replace the contents; .git stays.
find . -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -R "$source_dir/." .
cat > README.md <<README
# ${title}

**This repository is generated.** Every file is written by the [hub](${hub_url}) from each image's \`image.yml\`
and newest build, and pushed by its hourly refresh workflow; edits here are overwritten by the next run. Changes belong in
the image's repository (its \`image.yml\`) or in the hub's \`lsio_hub/generate/${platform}.py\`.

## Import

${how_to}

## Layout

${layout}

The same output is served at \`https://linuxserver-playground.github.io/hub/stores/${platform}/\`; the store index
with every platform is \`https://linuxserver-playground.github.io/hub/api/v1/stores/index.json\`.
README

git add -A
if git diff --cached --quiet; then
  echo "$repo: no changes"
  exit 0
fi
git commit --quiet -m "Update generated store"

if git push --quiet origin "HEAD:$branch"; then
  echo "$repo: pushed to $branch"
  exit 0
fi
echo "$repo: push rejected, rebasing once" >&2
git fetch --quiet origin "$branch"
# Ours is the generated snapshot: it wins every conflict (-X theirs applies to the replayed commit in a rebase).
git rebase --quiet -X theirs "origin/$branch"
git push --quiet origin "HEAD:$branch"
echo "$repo: pushed to $branch after rebase"
