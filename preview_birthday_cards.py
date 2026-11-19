"""Render birthday cards for every user with a birthday set, into a folder.

Preview-only tool: writes nothing to the DB and posts nothing to Discord.

    python preview_birthday_cards.py                     # all users with a birthday
    python preview_birthday_cards.py --limit 10          # first 10
    python preview_birthday_cards.py --guild 254779349352448001
    python preview_birthday_cards.py --debug-line        # draw the face-safe boundary
    python preview_birthday_cards.py --cake assets/cake.png
    python preview_birthday_cards.py --sheet             # also build a contact sheet

Outputs land in ./birthday_previews/ (gitignored) plus manifest.csv describing
what was rendered and how.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import random
import csv
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

import birthday_card

DB_PATH = Path("discord.db")
OUT_DIR = Path("birthday_previews")
UA = "rolm-birthday-card/1.0"

DEFAULT_AVATAR = "https://cdn.discordapp.com/embed/avatars/{idx}.png"


def avatar_url(user_id: str, avatar_hash: str | None) -> tuple[str, bool]:
    """Return (cdn_url, is_animated). Falls back to the default avatar."""
    if not avatar_hash:
        idx = (int(user_id) >> 22) % 6
        return DEFAULT_AVATAR.format(idx=idx), False
    animated = avatar_hash.startswith("a_")
    ext = "gif" if animated else "png"
    size = 256 if animated else 512  # Discord only serves animated at <=256
    return (
        f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}",
        animated,
    )


def _bot_token() -> str | None:
    env = Path(".env")
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        if line.startswith("TOKEN="):
            return line.split("=", 1)[1].strip()
    return None


def api_avatar_hash(user_id: str) -> str | None:
    """Ask Discord for the user's *current* avatar hash.

    The hash cached in discord.db goes stale whenever someone changes their PFP,
    and the CDN then 404s the old one.
    """
    import json

    token = _bot_token()
    if not token:
        return None
    req = urllib.request.Request(
        f"https://discord.com/api/v10/users/{user_id}",
        headers={"Authorization": f"Bot {token}", "User-Agent": UA},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("avatar")


def fetch(url: str, tries: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (404, 415):  # avatar gone or unservable
                raise
            time.sleep(1.5 * (attempt + 1))
        except Exception as e:  # noqa: BLE001 - transient network
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def load_users(db: Path, guild: str | None, limit: int | None):
    conn = sqlite3.connect(db)
    try:
        if guild:
            q = ("SELECT u.user_id, u.username, u.birthday, u.avatar "
                 "FROM users u JOIN user_guilds g ON g.user_id = u.user_id "
                 "WHERE u.birthday != '00-00' AND g.guild_id = ? "
                 "ORDER BY u.birthday, u.username")
            rows = conn.execute(q, (guild,)).fetchall()
        else:
            q = ("SELECT user_id, username, birthday, avatar FROM users "
                 "WHERE birthday != '00-00' ORDER BY birthday, username")
            rows = conn.execute(q).fetchall()
    finally:
        conn.close()
    return rows[:limit] if limit else rows


def safe_name(username: str) -> str:
    keep = "-_.() "
    cleaned = "".join(c if (c.isalnum() or c in keep) else "_" for c in username)
    return cleaned.strip().replace(" ", "_")[:40] or "unknown"


def build_sheet(files: list[Path], out: Path, cols: int = 8, cell: int = 128) -> Path | None:
    """Contact sheet so 100+ cards can be eyeballed in one image."""
    imgs = []
    for f in files:
        try:
            im = Image.open(f)
            if getattr(im, "is_animated", False):
                im.seek(0)
            imgs.append(im.convert("RGB").resize((cell, cell), Image.Resampling.LANCZOS))
        except Exception:
            continue
    if not imgs:
        return None
    rows = (len(imgs) + cols - 1) // cols
    gap = 4
    sheet = Image.new("RGB", (cols * (cell + gap) + gap, rows * (cell + gap) + gap), (24, 24, 28))
    for i, im in enumerate(imgs):
        x = gap + (i % cols) * (cell + gap)
        y = gap + (i // cols) * (cell + gap)
        sheet.paste(im, (x, y))
    sheet.save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--guild", default=None, help="limit to one guild id")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--size", type=int, default=birthday_card.CARD_SIZE)
    ap.add_argument("--cake", default=None, help="transparent PNG to use instead of the drawn cake")
    ap.add_argument("--debug-line", action="store_true", help="draw the face-safe boundary")
    ap.add_argument("--sheet", action="store_true", help="also write a contact sheet")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    users = load_users(Path(args.db), args.guild, args.limit)
    print(f"users with a birthday: {len(users)}")

    def work(row):
        user_id, username, bday, avatar_hash = row
        # A NULL avatar means the row was written before the hash was ever
        # captured (or it was cleared), NOT that the user has no PFP. Ask
        # Discord for the current hash instead of drawing their default icon.
        refreshed = False
        if not avatar_hash:
            try:
                avatar_hash = api_avatar_hash(user_id)
                refreshed = bool(avatar_hash)
            except Exception:
                avatar_hash = None
        url, animated = avatar_url(user_id, avatar_hash)
        # Seeded per user so re-running the preview keeps the same cupcake for
        # each person and the sheet is comparable between runs.
        decoration = birthday_card.pick_food(random.Random(user_id))
        started = time.time()
        source = "api-refresh" if refreshed else (
            "animated" if animated else ("default" if not avatar_hash else "static"))
        try:
            try:
                raw = fetch(url)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
                # Stale hash: ask Discord for the current one, then retry.
                fresh = api_avatar_hash(user_id)
                if fresh and fresh != avatar_hash:
                    url, animated = avatar_url(user_id, fresh)
                    source = "api-refresh"
                    raw = fetch(url)
                else:
                    url, animated = avatar_url(user_id, None)
                    source = "default"
                    raw = fetch(url)
            ext = ".gif" if animated else ".png"   # temp PFP keeps its own form
            tmp = out_dir / f".tmp_{user_id}{ext}"
            tmp.write_bytes(raw)
            dest = out_dir / f"{bday}_{safe_name(username)}.webp"
            out_path = birthday_card.render_file(
                tmp, username, dest, size=args.size,
                cake_path=args.cake or decoration,
                debug_safe_line=args.debug_line,
            )
            tmp.unlink(missing_ok=True)
            out_im = Image.open(out_path)
            return {
                "user_id": user_id, "username": username, "birthday": bday,
                "source": source,
                "animated_out": bool(getattr(out_im, "is_animated", False)),
                "frames": getattr(out_im, "n_frames", 1),
                "decoration": decoration.name if decoration else "drawn",
                "bytes": out_path.stat().st_size,
                "seconds": round(time.time() - started, 2),
                "file": out_path.name, "error": "",
            }
        except Exception as e:  # noqa: BLE001 - report, don't abort the batch
            return {
                "user_id": user_id, "username": username, "birthday": bday,
                "source": "animated" if animated else "static",
                "animated_out": False, "frames": 0, "bytes": 0,
                "seconds": round(time.time() - started, 2),
                "file": "", "error": f"{type(e).__name__}: {e}",
            }

    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(work, users):
            rows.append(res)
            flag = "ERR " + res["error"] if res["error"] else "ok"
            print(f"  {res['birthday']}  {res['username'][:28]:<28} "
                  f"{res['source']:<9} {res['frames']:>2}f "
                  f"{res['bytes']/1024:>7.1f}KB {res['seconds']:>5.2f}s  {flag}")

    manifest = out_dir / "manifest.csv"
    with manifest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)

    ok = [r for r in rows if not r["error"]]
    anim = [r for r in ok if r["animated_out"]]
    print(f"\nrendered {len(ok)}/{len(rows)}  ({len(anim)} animated)  -> {out_dir}")
    if len(ok) != len(rows):
        print("failures:")
        for r in rows:
            if r["error"]:
                print(f"  {r['username']} ({r['user_id']}): {r['error']}")

    if args.sheet:
        files = [out_dir / r["file"] for r in ok]
        sheet = build_sheet(files, out_dir / "contact_sheet.webp")
        print(f"contact sheet -> {sheet}")


if __name__ == "__main__":
    main()
