#!/usr/bin/env bash
# Self-healing deploy: if the live site is behind the repo and no deploy is making
# progress, start a fresh one. Runs on every bot poll (see telegram.yml).
#
# Why: GitHub Pages deploys occasionally hang on the final "deploy-pages" step
# (seen 2026-10-14: in_progress for 6+ min, normally ~1 min). The bot only starts a
# deploy when it has new content, so a hung deploy left the site stale until the
# next post. Needs GH_TOKEN (actions: write). DRY_RUN=1 prints instead of acting.
set -u
REPO="${GITHUB_REPOSITORY:-maxtindall/maxis.fit}"
SITE="https://maxis.fit"
# seconds a deploy may take before it counts as stuck. Pages deploys normally take ~1 min but
# were seen taking 6 min (2026-10-14); deploy-pages itself gives up after 10, so 11 is "stuck".
GRACE="${GRACE:-660}"

act() { if [ "${DRY_RUN:-0}" = 1 ]; then echo "DRY RUN: $*"; else "$@"; fi; }

# 1. is the live site in sync with the repo? (data files are what the bot changes)
stale=0
for f in updates.json works.json; do
  live=$(curl -fsS --max-time 20 "$SITE/$f?$(date +%s)" | sha256sum | cut -d' ' -f1) || { echo "site unreachable, skipping"; exit 0; }
  repo=$(sha256sum "$f" | cut -d' ' -f1)
  [ "$live" = "$repo" ] || { echo "live $f differs from repo"; stale=1; }
done
[ "$stale" = 0 ] && { echo "live site is in sync"; exit 0; }

# 2. look at the newest site deploy run
read -r id status created < <(gh run list --repo "$REPO" --workflow site.yml --limit 1 \
  --json databaseId,status,createdAt -q '.[0] | "\(.databaseId) \(.status) \(.createdAt)"')
age=$(python3 -c "import sys,datetime as d; print(int((d.datetime.now(d.timezone.utc)-d.datetime.fromisoformat(sys.argv[1].replace('Z','+00:00'))).total_seconds()))" "$created")
echo "newest deploy: run $id is $status, started ${age}s ago"

# 3. recent deploy: give it time. Old and unfinished: cancel it. Then start a fresh one.
if [ "$age" -lt "$GRACE" ]; then echo "recent enough, waiting"; exit 0; fi
case "$status" in
  in_progress|queued|waiting|pending) echo "deploy looks stuck, cancelling run $id"; act gh run cancel "$id" --repo "$REPO" || true ;;
esac
echo "starting a fresh deploy"
act gh workflow run site.yml --repo "$REPO"
