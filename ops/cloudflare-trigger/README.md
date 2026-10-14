# Telegram bot trigger (Cloudflare cron)

GitHub's `schedule:` trigger is throttled on quiet repos and can go hours
between runs. This Worker calls `workflow_dispatch` on `telegram.yml` every
2 minutes instead. The bot itself still runs in GitHub Actions.

## One-time setup

1. **GitHub token** (limited to this repo):
   github.com/settings/personal-access-tokens/new
   - Repository access: *Only select repositories* -> `maxtindall/maxis.fit`
   - Permissions: *Actions: Read and write* (Metadata read is added automatically)
   - Pick a long expiry; note the date so you can renew it.
2. **Cloudflare**: free account at dash.cloudflare.com, then from this folder:

   ```bash
   npx wrangler login
   npx wrangler deploy
   npx wrangler secret put GITHUB_TOKEN   # paste the token when prompted
   ```

3. **Check it**: `gh run list --workflow=telegram.yml --repo maxtindall/maxis.fit`
   should show a `workflow_dispatch` run every ~2 minutes. Errors from the
   Worker (bad or expired token) show in Cloudflare: Workers -> maxisfit-bot-trigger -> Logs.

## Changing things

- Frequency: edit `crons` in `wrangler.toml`, then `npx wrangler deploy`.
- Rotate the token: `npx wrangler secret put GITHUB_TOKEN` again.
- Stop it: `npx wrangler delete`.
