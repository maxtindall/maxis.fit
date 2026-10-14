// Starts the maxis.fit Telegram bot workflow on a reliable schedule.
// GitHub's own `schedule:` trigger is throttled on quiet repos (hours between
// runs), so Cloudflare's cron triggers call workflow_dispatch instead.
// Needs one secret: GITHUB_TOKEN (fine-grained, this repo only, Actions: read/write).

const REPO = "maxtindall/maxis.fit";
const WORKFLOW = "telegram.yml";

async function dispatch(env) {
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "maxisfit-bot-trigger",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  // GitHub answers 204 No Content on success
  if (res.status !== 204) {
    console.log(`dispatch failed: ${res.status} ${await res.text()}`);
  }
  return res.status;
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },
  // nothing to serve; keeps the worker URL boring
  async fetch() {
    return new Response("maxisfit-bot-trigger", { status: 200 });
  },
};
