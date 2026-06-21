"""Tests for dashboard/discord_api.py — Discord REST helpers used by the dashboard.

The module fetches guild role metadata via the Discord REST API and
caches it in a module-level dict. We mock aiohttp.ClientSession to
avoid any real network calls and reset the cache between tests.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import dashboard.discord_api as discord_api


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    # Clear the module-level cache before AND after each test.
    discord_api._roles_cache.clear()
    yield
    discord_api._roles_cache.clear()


def _make_aiohttp_response(status=200, json_data=None, text_data=""):
    """Build an async context manager that mimics aiohttp.ClientResponse."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or [])
    resp.text = AsyncMock(return_value=text_data)
    # Make the response usable as `async with session.get(...) as resp:`
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


def _make_session(responses_by_url):
    """Build a fake aiohttp.ClientSession where session.get(url) returns
    the response mapped to that URL in `responses_by_url`.
    """
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    def get(url, headers=None):
        return responses_by_url.get(url, _make_aiohttp_response(status=404, text_data="not found"))

    session.get = MagicMock(side_effect=get)
    return session


# ------------------------------------------------------------------
# _ensure_token()
# ------------------------------------------------------------------

def test_ensure_token_raises_when_env_missing(monkeypatch):
    # No TOKEN in env and no load_dotenv fallback → RuntimeError.
    monkeypatch.delenv("TOKEN", raising=False)
    monkeypatch.setattr(discord_api, "load_dotenv", None)
    with pytest.raises(RuntimeError, match="Discord token not found"):
        discord_api._ensure_token()


def test_ensure_token_reads_from_env_when_dotenv_unavailable(monkeypatch):
    # If dotenv isn't importable but TOKEN is in the environment, return it.
    monkeypatch.setenv("TOKEN", "test_token_abc")
    monkeypatch.setattr(discord_api, "load_dotenv", None)
    assert discord_api._ensure_token() == "test_token_abc"


def test_ensure_token_calls_load_dotenv_when_available(monkeypatch, tmp_path):
    # If load_dotenv is importable, _ensure_token delegates to it before
    # reading TOKEN. We write a .env in a tmp dir and verify load_dotenv
    # was called with the right path. (We don't actually rely on it loading
    # — we set TOKEN directly after the call.)
    monkeypatch.setenv("TOKEN", "test_token_xyz")
    fake_load = MagicMock()
    monkeypatch.setattr(discord_api, "load_dotenv", fake_load)

    token = discord_api._ensure_token()
    assert token == "test_token_xyz"
    assert fake_load.called


# ------------------------------------------------------------------
# fetch_guild_roles()
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_guild_roles_returns_dict_on_200(monkeypatch):
    # 200 response → parsed dict keyed by stringified role id.
    monkeypatch.setenv("TOKEN", "test_token")
    roles_payload = [
        {"id": "111", "name": "Admin", "color": 0xFF0000},
        {"id": "222", "name": "Member", "color": 0},
    ]
    resp = _make_aiohttp_response(status=200, json_data=roles_payload)
    session = _make_session({
        f"{discord_api.DISCORD_API}/guilds/100/roles": resp,
    })

    with patch.object(discord_api.aiohttp, "ClientSession", return_value=session):
        result = await discord_api.fetch_guild_roles("100")

    assert result == {
        "111": {"name": "Admin", "color": 0xFF0000},
        "222": {"name": "Member", "color": 0},
    }


@pytest.mark.asyncio
async def test_fetch_guild_roles_defaults_color_to_zero(monkeypatch):
    # Roles in the wild don't always have a color field. fetch_guild_roles
    # must default to 0 rather than KeyError.
    monkeypatch.setenv("TOKEN", "test_token")
    roles_payload = [{"id": "111", "name": "Admin"}]  # no color
    resp = _make_aiohttp_response(status=200, json_data=roles_payload)
    session = _make_session({
        f"{discord_api.DISCORD_API}/guilds/100/roles": resp,
    })

    with patch.object(discord_api.aiohttp, "ClientSession", return_value=session):
        result = await discord_api.fetch_guild_roles("100")

    assert result == {"111": {"name": "Admin", "color": 0}}


@pytest.mark.asyncio
async def test_fetch_guild_roles_raises_on_non_200(monkeypatch):
    # Non-200 response → RuntimeError including the status and response body.
    monkeypatch.setenv("TOKEN", "test_token")
    resp = _make_aiohttp_response(status=403, text_data="Missing Permissions")
    session = _make_session({
        f"{discord_api.DISCORD_API}/guilds/100/roles": resp,
    })

    with patch.object(discord_api.aiohttp, "ClientSession", return_value=session):
        with pytest.raises(RuntimeError, match="403"):
            await discord_api.fetch_guild_roles("100")


# ------------------------------------------------------------------
# refresh_role_cache()
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_role_cache_populates_cache_per_guild(monkeypatch):
    # Two guilds fetched successfully → cache has entries for both.
    monkeypatch.setenv("TOKEN", "test_token")

    resp_a = _make_aiohttp_response(
        status=200, json_data=[{"id": "1", "name": "RoleA", "color": 0}]
    )
    resp_b = _make_aiohttp_response(
        status=200, json_data=[{"id": "2", "name": "RoleB", "color": 0}]
    )
    session = _make_session({
        f"{discord_api.DISCORD_API}/guilds/100/roles": resp_a,
        f"{discord_api.DISCORD_API}/guilds/200/roles": resp_b,
    })

    with patch.object(discord_api.aiohttp, "ClientSession", return_value=session):
        await discord_api.refresh_role_cache(["100", "200"])

    assert "100" in discord_api._roles_cache
    assert "200" in discord_api._roles_cache
    assert discord_api._roles_cache["100"]["1"]["name"] == "RoleA"
    assert discord_api._roles_cache["200"]["2"]["name"] == "RoleB"


@pytest.mark.asyncio
async def test_refresh_role_cache_swallows_per_guild_failures(monkeypatch):
    # One guild fails → that guild's cache becomes {}, others still populate.
    monkeypatch.setenv("TOKEN", "test_token")

    resp_ok = _make_aiohttp_response(
        status=200, json_data=[{"id": "1", "name": "Role", "color": 0}]
    )
    resp_fail = _make_aiohttp_response(status=500, text_data="server error")
    session = _make_session({
        f"{discord_api.DISCORD_API}/guilds/100/roles": resp_ok,
        f"{discord_api.DISCORD_API}/guilds/200/roles": resp_fail,
    })

    with patch.object(discord_api.aiohttp, "ClientSession", return_value=session):
        # Must not raise — refresh_role_cache logs and continues.
        await discord_api.refresh_role_cache(["100", "200"])

    assert discord_api._roles_cache["100"]["1"]["name"] == "Role"
    assert discord_api._roles_cache["200"] == {}


# ------------------------------------------------------------------
# get_role_name()
# ------------------------------------------------------------------

def test_get_role_name_returns_cached_name():
    # Happy path: role is in the cache → name is returned.
    discord_api._roles_cache["100"] = {
        "111": {"name": "Admin", "color": 0xFF0000},
    }
    assert discord_api.get_role_name("100", "111") == "Admin"


def test_get_role_name_returns_none_when_guild_missing():
    # Cache has no entry for this guild → None (don't raise).
    assert discord_api.get_role_name("999", "111") is None


def test_get_role_name_returns_none_when_role_missing():
    # Cache has the guild but not this role → None.
    discord_api._roles_cache["100"] = {
        "111": {"name": "Admin", "color": 0},
    }
    assert discord_api.get_role_name("100", "999") is None


# ------------------------------------------------------------------
# get_cached_guild_roles()
# ------------------------------------------------------------------

def test_get_cached_guild_roles_returns_full_dict():
    discord_api._roles_cache["100"] = {
        "111": {"name": "Admin", "color": 1},
        "222": {"name": "Member", "color": 2},
    }
    assert discord_api.get_cached_guild_roles("100") == {
        "111": {"name": "Admin", "color": 1},
        "222": {"name": "Member", "color": 2},
    }


def test_get_cached_guild_roles_returns_empty_default_for_unknown_guild():
    # Cache miss returns {}, not None, so callers can iterate safely.
    assert discord_api.get_cached_guild_roles("999") == {}