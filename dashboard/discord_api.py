"""Discord REST helpers for the Rolm Dashboard.
Fetches guild role metadata (names, colors, etc.) using a bot token.
"""
import os
import asyncio
import aiohttp
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

DISCORD_API = "https://discord.com/api/v10"
# Cache: {guild_id: {role_id_str: {"name": str, "color": int, ...}}}
_roles_cache: dict = {}
_cache_lock = asyncio.Lock()


def _ensure_token():
    if load_dotenv:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(dotenv_path=env_path)
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("Discord token not found. Set TOKEN in .env")
    return token


async def fetch_guild_roles(guild_id: str) -> dict:
    """Fetch all roles for a guild from Discord API. Returns {role_id: {...}}."""
    token = _ensure_token()
    headers = {"Authorization": f"Bot {token}"}
    url = f"{DISCORD_API}/guilds/{guild_id}/roles"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                roles = await resp.json()
                return {str(r["id"]): {"name": r["name"], "color": r.get("color", 0)} for r in roles}
            else:
                text = await resp.text()
                raise RuntimeError(f"Discord API {resp.status}: {text}")


async def refresh_role_cache(guild_ids: list[str]):
    """Populate the in-memory role cache for the given guild IDs."""
    global _roles_cache
    async with _cache_lock:
        for gid in guild_ids:
            try:
                _roles_cache[gid] = await fetch_guild_roles(gid)
                import sys
                sys.stderr.write(f"[discord_api] cached {len(_roles_cache[gid])} roles for guild {gid}\n")
            except Exception as e:
                import sys
                sys.stderr.write(f"[discord_api] ERROR fetching roles for guild {gid}: {e}\n")
                _roles_cache[gid] = {}


def get_role_name(guild_id: str, role_id: str) -> str | None:
    """Return a cached role name or None if not present."""
    guild = _roles_cache.get(guild_id, {})
    role = guild.get(role_id)
    if role:
        return role.get("name")
    return None


def get_cached_guild_roles(guild_id: str) -> dict:
    """Return the full cached role map for a guild."""
    return _roles_cache.get(guild_id, {})
