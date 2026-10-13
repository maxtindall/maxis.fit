"""Telegram bot for maxis.fit. Pulls new messages and applies them to the repo.

Only messages from TELEGRAM_USER_ID are acted on. Everything else is ignored.

  plain text                 -> homepage update (updates.json)
  photo / image file         -> new work in selected work (works.json); the
                                caption becomes the label text. Send as a FILE
                                to keep full resolution.
  /caption N new text        -> change the label text of work N
  /remove N                  -> remove work N (later works renumber)
  /move N M                  -> move work N to position M
  /list                      -> reply with all works
  /help                      -> reply with this list

Work numbers are automatic: the position in works.json, zero-padded by the
page. Prints "changed" on stdout when any data file was modified.
"""
import io, json, os, re, sys, urllib.request, urllib.parse
from datetime import datetime, timezone

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER = int(os.environ["TELEGRAM_USER_ID"].strip())
API = f"https://api.telegram.org/bot{TOKEN}/"
FILES = f"https://api.telegram.org/file/bot{TOKEN}/"
UPDATES, WORKS = "updates.json", "works.json"
WORKS_DIR = "works"
MAX_UPDATE, MAX_CAPTION, WEB_EDGE = 280, 200, 1600
SHARP_EDGE = 2000  # below this long edge, deep zoom looks soft

HELP = ("Text: homepage update.\n"
        "Photo or image file + caption: new work (send as file for full res).\n"
        "/caption N text, /remove N, /move N M, /list")


def call(method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(API + method, data) as r:
        return json.load(r)


def reply(chat_id, text):
    try:
        call("sendMessage", chat_id=chat_id, text=text)
    except Exception as e:  # a failed reply must never break the run
        print(f"reply failed: {e}", file=sys.stderr)


def download(file_id):
    info = call("getFile", file_id=file_id)["result"]
    with urllib.request.urlopen(FILES + info["file_path"]) as r:
        return r.read()


def load(path, default):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        return default


def save(path, data):
    json.dump(data, open(path, "w"), indent=1, ensure_ascii=False)


def tidy_caption(text):
    """House style: each comma segment capitalised, ends with a full stop."""
    text = " ".join(text.split())[:MAX_CAPTION] or "Untitled"
    text = re.sub(r"(^|,\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text if text[-1] in ".!?" else text + "."


def add_work(works, m, update_id):
    """Save a photo or image file and append it to works. Returns reply text."""
    from PIL import Image, ImageOps

    if m.get("photo"):
        file_id, is_file = m["photo"][-1]["file_id"], False  # largest size
    else:
        file_id, is_file = m["document"]["file_id"], True
    raw = download(file_id)
    try:
        src_im = Image.open(io.BytesIO(raw))
        fmt = (src_im.format or "").upper()
        im = ImageOps.exif_transpose(src_im)
    except Exception:
        return "Could not read that image. Send a JPG or PNG."
    if fmt not in ("JPEG", "PNG"):
        return f"{fmt or 'That'} images are not supported. Send a JPG or PNG."

    os.makedirs(WORKS_DIR, exist_ok=True)
    stem = f"{WORKS_DIR}/w{update_id}"
    ext = "png" if fmt == "PNG" else "jpg"
    web = im.convert("RGB")
    web.thumbnail((WEB_EDGE, WEB_EDGE))
    web.save(f"{stem}_web.jpg", "JPEG", quality=85, optimize=True)
    if is_file:
        open(f"{stem}.{ext}", "wb").write(raw)  # untouched original for zoom
        full = f"{stem}.{ext}"
    else:  # telegram already compressed it: web copy doubles as full
        full = f"{stem}_web.jpg"
    works.append({"src": f"{stem}_web.jpg", "full": full,
                  "caption": tidy_caption(m.get("caption") or "")})
    msg = f"Added as {len(works):03d}: {works[-1]['caption']}"
    w, h = im.size
    if max(w, h) < SHARP_EDGE:
        how = ("it was sent as a photo, which Telegram compresses"
               if not is_file else "the file itself is small")
        msg += (f"\n\nHeads up: {how}, so this is only {w}x{h} and deep zoom "
                f"will look soft. For sharp zoom, /remove {len(works)} and "
                "send the original again as a file (attach > File).")
    return msg


def parse_n(works, token):
    n = int(token)
    if not 1 <= n <= len(works):
        raise ValueError
    return n


def command(works, text):
    """Handle a /command on works. Returns (reply text, works_changed)."""
    parts = text.split(None, 2)
    cmd = parts[0].split("@")[0].lower()
    try:
        if cmd == "/list":
            if not works:
                return "No works yet.", False
            return "\n".join(f"{i:03d}. {w['caption']}"
                             for i, w in enumerate(works, 1)), False
        if cmd == "/caption":
            n = parse_n(works, parts[1])
            works[n - 1]["caption"] = tidy_caption(parts[2])
            return f"{n:03d}: {works[n - 1]['caption']}", True
        if cmd == "/remove":
            n = parse_n(works, parts[1])
            w = works.pop(n - 1)
            for p in {w["src"], w["full"]}:
                # only ever delete bot-managed files
                if p.startswith(WORKS_DIR + "/") and os.path.exists(p):
                    os.remove(p)
            return f"Removed {n:03d}. {len(works)} works left.", True
        if cmd == "/move":
            n, to = parse_n(works, parts[1]), parse_n(works, parts[2])
            works.insert(to - 1, works.pop(n - 1))
            return f"Moved {n:03d} to {to:03d}.", True
    except (IndexError, ValueError):
        return "Bad command. " + HELP, False
    return HELP, False


def main():
    updates = load(UPDATES, {"offset": 0, "updates": []})
    works = load(WORKS, {"works": []})
    resp = call("getUpdates", offset=updates["offset"], timeout=0,
                allowed_updates=json.dumps(["message"]))
    if not resp.get("ok"):
        sys.exit("telegram error")

    changed = {"updates": False, "works": False}
    for u in resp["result"]:
        updates["offset"] = u["update_id"] + 1
        changed["updates"] = True
        m = u.get("message") or {}
        if m.get("from", {}).get("id") != OWNER:
            continue
        chat = m["chat"]["id"]
        text = (m.get("text") or "").strip()
        try:
            if m.get("photo") or (m.get("document", {}).get("mime_type", "")
                                  .startswith("image/")):
                msg = add_work(works["works"], m, u["update_id"])
                changed["works"] |= msg.startswith("Added")
                reply(chat, msg)
            elif text.startswith("/"):
                msg, did = command(works["works"], text)
                changed["works"] |= did
                reply(chat, msg)
            elif text:
                updates["updates"].append({
                    "date": datetime.fromtimestamp(
                        m["date"], timezone.utc).isoformat(),
                    "text": text[:MAX_UPDATE]})
                reply(chat, "Posted.")
        except Exception as e:  # one bad message must not block the queue
            print(f"failed on update {u['update_id']}: {e}", file=sys.stderr)
            reply(chat, "Something went wrong with that message.")

    if changed["updates"]:
        save(UPDATES, updates)
    if changed["works"]:
        save(WORKS, works)
    if any(changed.values()):
        print("changed")


main()
