#!/usr/bin/env python3
"""One-off script to populate avatar hashes for all existing users."""
import os
import sqlite3
import asyncio
import aiohttp

from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")
DISCORD_API = "https://discord.com/api/v10"
DB_PATH = "/root/projects/Discord-Role-Manager/discord.db"

async def fetch_user_avatar(session: aiohttp.ClientSession, user_id: str) -> str | None:
    headers = {"Authorization": f"Bot {TOKEN}"}
    url = f"{DISCORD_API}/users/{user_id}"
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("avatar")
            else:
                print(f"  Error {resp.status} for user {user_id}")
                return None
    except Exception as e:
        print(f"  Exception for user {user_id}: {e}")
        return None

async def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in c.fetchall()]
    conn.close()

    print(f"Found {len(user_ids)} users to update")

    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as session:
        updated = 0
        skipped = 0
        for i, uid in enumerate(user_ids):
            avatar = await fetch_user_avatar(session, uid)
            if avatar:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE users SET avatar = ? WHERE user_id = ?", (avatar, uid))
                conn.commit()
                conn.close()
                updated += 1
                if updated % 50 == 0:
                    print(f"  ... updated {updated} so far")
            else:
                skipped += 1
            # Sleep every 50 requests to stay under rate limits
            if (i + 1) % 50 == 0:
                await asyncio.sleep(1)

    print(f"Done! Updated {updated} users, skipped {skipped}.")

if __name__ == "__main__":
    asyncio.run(main())
