"""Tests for fetch_avatars.py — one-off backfill script for avatar hashes.

The script has one non-trivial function (fetch_user_avatar) plus a
main() runner. main() does direct sqlite3 + aiohttp work against a
hardcoded DB_PATH, so we keep tests focused on fetch_user_avatar.
"""
import builtins
from unittest.mock import AsyncMock, MagicMock

import pytest

import fetch_avatars


def _make_response(status=200, json_data=None):
    """Async context manager mimicking aiohttp.ClientResponse."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


def _make_session(response):
    session = MagicMock()
    session.get = MagicMock(return_value=response)
    return session


# ------------------------------------------------------------------
# fetch_user_avatar()
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_user_avatar_returns_hash_on_200():
    resp = _make_response(status=200, json_data={"avatar": "abc123hash"})
    session = _make_session(resp)
    result = await fetch_avatars.fetch_user_avatar(session, "111")
    assert result == "abc123hash"
    session.get.assert_called_once()
    called_url = session.get.call_args[0][0]
    assert "/users/111" in called_url


@pytest.mark.asyncio
async def test_fetch_user_avatar_returns_none_when_avatar_field_missing():
    # 200 but the user has no custom avatar (data["avatar"] is None).
    resp = _make_response(status=200, json_data={"avatar": None})
    session = _make_session(resp)
    result = await fetch_avatars.fetch_user_avatar(session, "111")
    assert result is None


@pytest.mark.asyncio
async def test_fetch_user_avatar_returns_none_on_non_200(capsys):
    # Non-200 → None, with an error message printed to stdout.
    resp = _make_response(status=404)
    session = _make_session(resp)
    result = await fetch_avatars.fetch_user_avatar(session, "111")
    assert result is None
    captured = capsys.readouterr()
    assert "Error 404" in captured.out
    assert "111" in captured.out


@pytest.mark.asyncio
async def test_fetch_user_avatar_returns_none_on_exception(capsys):
    # Network/timeout/etc → None, with exception details printed.
    session = MagicMock()
    session.get = MagicMock(side_effect=RuntimeError("network down"))

    result = await fetch_avatars.fetch_user_avatar(session, "111")
    assert result is None
    captured = capsys.readouterr()
    assert "Exception for user 111" in captured.out
    assert "network down" in captured.out


@pytest.mark.asyncio
async def test_fetch_user_avatar_passes_bot_auth_header():
    # The Authorization header must be 'Bot <token>' — not 'Bearer <token>'
    # or anything else. Discord rejects bearer auth for bot endpoints.
    resp = _make_response(status=200, json_data={"avatar": "x"})
    session = _make_session(resp)
    await fetch_avatars.fetch_user_avatar(session, "111")
    headers = session.get.call_args[1]["headers"]
    assert headers["Authorization"].startswith("Bot ")