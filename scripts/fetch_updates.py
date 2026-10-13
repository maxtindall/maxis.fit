"""Pull new Telegram messages from the bot into updates.json.

Only messages from TELEGRAM_USER_ID are kept. Exits 0 and prints
"changed" when updates.json was modified.
"""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timezone

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER = int(os.environ["TELEGRAM_USER_ID"])
PATH = "updates.json"
MAX_LEN = 280

data = json.load(open(PATH))
qs = urllib.parse.urlencode({"offset": data["offset"], "timeout": 0,
                             "allowed_updates": json.dumps(["message"])})
with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getUpdates?{qs}") as r:
    resp = json.load(r)
if not resp.get("ok"):
    sys.exit("telegram error")

changed = False
for u in resp["result"]:
    data["offset"] = u["update_id"] + 1
    changed = True
    m = u.get("message") or {}
    text = (m.get("text") or "").strip()
    if m.get("from", {}).get("id") != OWNER or not text or text.startswith("/"):
        continue
    data["updates"].append({
        "date": datetime.fromtimestamp(m["date"], timezone.utc).isoformat(),
        "text": text[:MAX_LEN],
    })

if changed:
    json.dump(data, open(PATH, "w"), indent=1, ensure_ascii=False)
    print("changed")
