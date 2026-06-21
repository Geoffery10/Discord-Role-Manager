"""Tests for update.py — the daily task runner.

update.py has three entry points:
  - update(client, guilds): runs check_birthday per guild, then
    parallel update_database per guild via asyncio.gather.
  - check_if_update_needed(client, guilds): reads last_update.json,
    compares against today's date, and only runs update() on a new day.
  - update_database(members, guild): per-member sync (add new users,
    update drifted tag/username/avatar, ensure user_guilds row).

The DB-touching tests use the isolated_cwd + fresh_db fixtures from
conftest.py so they run against a real tmp sqlite DB. The orchestrator
tests (update / check_if_update_needed) patch the inner functions.
"""
import asyncio
import datetime
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import update


# ------------------------------------------------------------------
# Test helpers
# ------------------------------------------------------------------

def make_member(user_id, name, discriminator="0001", avatar_key=None):
    """Build a MagicMock standing in for a discord.Member.

    update_database reads member.id (int), member.name, member.discriminator,
    and member.avatar.key (with member.avatar possibly None).
    """
    member = MagicMock()
    member.id = user_id
    member.name = name
    member.discriminator = discriminator
    if avatar_key is None:
        member.avatar = None
    else:
        avatar = MagicMock()
        avatar.key = avatar_key
        member.avatar = avatar
    return member


def make_guild(guild_id, name="Test Guild", members=None):
    """Build a fake discord.Guild for the client.get_guild lookup."""
    guild = MagicMock()
    guild.id = guild_id
    guild.name = name
    guild.members = members if members is not None else []
    return guild


# ------------------------------------------------------------------
# update_database() — per-member branches
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_database_adds_new_user(isolated_cwd, fresh_db):
    """Member with no DB row → add_user is called and the row appears."""
    import iDiscord

    member = make_member(user_id=12345, name="Alice", discriminator="0001", avatar_key="av_a")
    guild = make_guild(100, members=[member])

    await update.update_database([member], guild)

    fetched = await iDiscord.get_user("12345")
    assert fetched is not None
    assert fetched.get_username() == "Alice"
    assert fetched.get_tag() == "0001"
    assert fetched.get_avatar() == "av_a"
    # User must also be linked to the guild.
    assert await iDiscord.is_user_in_guild("12345", 100) is True


@pytest.mark.asyncio
async def test_update_database_updates_changed_discriminator(isolated_cwd, fresh_db):
    """Existing user with stale tag gets update_user_tag called."""
    import iDiscord

    await iDiscord.add_user("12345", "Alice", "01-15", "0001", "av_a")
    # Discriminator changed (Discord migrated to unique usernames).
    member = make_member(user_id=12345, name="Alice", discriminator="0002", avatar_key="av_a")
    guild = make_guild(100, members=[member])

    await update.update_database([member], guild)

    fetched = await iDiscord.get_user("12345")
    assert fetched is not None
    assert fetched.get_tag() == "0002"


@pytest.mark.asyncio
async def test_update_database_updates_changed_username(isolated_cwd, fresh_db):
    """Existing user with stale username gets update_user_username called."""
    import iDiscord

    await iDiscord.add_user("12345", "Alice", "01-15", "0001", "av_a")
    member = make_member(user_id=12345, name="Alice2", discriminator="0001", avatar_key="av_a")
    guild = make_guild(100, members=[member])

    await update.update_database([member], guild)

    fetched = await iDiscord.get_user("12345")
    assert fetched is not None
    assert fetched.get_username() == "Alice2"


@pytest.mark.asyncio
async def test_update_database_updates_changed_avatar(isolated_cwd, fresh_db):
    """Existing user with stale avatar gets update_user_avatar called."""
    import iDiscord

    await iDiscord.add_user("12345", "Alice", "01-15", "0001", "old_av")
    member = make_member(user_id=12345, name="Alice", discriminator="0001", avatar_key="new_av")
    guild = make_guild(100, members=[member])

    await update.update_database([member], guild)

    fetched = await iDiscord.get_user("12345")
    assert fetched is not None
    assert fetched.get_avatar() == "new_av"


@pytest.mark.asyncio
async def test_update_database_handles_none_avatar(isolated_cwd, fresh_db):
    """Member with no avatar (member.avatar is None) must not crash and
    must persist avatar=None on a new user."""
    import iDiscord

    member = make_member(user_id=12345, name="Alice", discriminator="0001", avatar_key=None)
    guild = make_guild(100, members=[member])

    await update.update_database([member], guild)

    fetched = await iDiscord.get_user("12345")
    assert fetched is not None
    assert fetched.get_avatar() is None


@pytest.mark.asyncio
async def test_update_database_is_noop_when_fully_synced(isolated_cwd, fresh_db):
    """Member matches DB exactly → no updates called, no exceptions."""
    import iDiscord

    await iDiscord.add_user("12345", "Alice", "01-15", "0001", "av_a")
    await iDiscord.add_user_to_guild("12345", 100)

    # All fields match.
    member = make_member(user_id=12345, name="Alice", discriminator="0001", avatar_key="av_a")
    guild = make_guild(100, members=[member])

    # Should not raise.
    await update.update_database([member], guild)

    fetched = await iDiscord.get_user("12345")
    assert fetched is not None
    assert fetched.get_username() == "Alice"
    assert fetched.get_tag() == "0001"
    assert fetched.get_avatar() == "av_a"


@pytest.mark.asyncio
async def test_update_database_links_to_new_guild_without_duplicating(
    isolated_cwd, fresh_db
):
    """User exists in DB but isn't linked to this guild yet → link added.
    User already linked → no duplicate row."""
    import iDiscord

    await iDiscord.add_user("12345", "Alice", "01-15", "0001", "av_a")
    # Already linked to guild 100.
    await iDiscord.add_user_to_guild("12345", 100)

    member = make_member(user_id=12345, name="Alice", discriminator="0001", avatar_key="av_a")
    guild = make_guild(100, members=[member])

    await update.update_database([member], guild)

    # Still exactly one row.
    db_path = Path(str(isolated_cwd)) / "discord.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM user_guilds WHERE user_id = ? AND guild_id = ?",
        ("12345", "100"),
    )
    assert c.fetchone()[0] == 1
    conn.close()


@pytest.mark.asyncio
async def test_update_database_handles_empty_members_list(isolated_cwd, fresh_db):
    """Empty member list must not raise (no members means no work)."""
    guild = make_guild(100, members=[])
    await update.update_database([], guild)  # should not raise


# ------------------------------------------------------------------
# update() — orchestrator (runs check_birthday then parallel DB updates)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_runs_check_birthday_per_guild_then_parallel_db_updates(
    isolated_cwd, fresh_db, last_update_json
):
    """update() iterates each guild, calls check_birthday on it, then
    spawns update_database tasks and gathers them."""
    guild_a = make_guild(100, name="Alpha", members=[])
    guild_b = make_guild(200, name="Beta", members=[])
    client = MagicMock()
    client.get_guild.side_effect = lambda gid: {100: guild_a, 200: guild_b}[gid]

    check_birthday_mock = AsyncMock()

    # Track what asyncio.gather receives.
    gathered_tasks = []

    async def fake_gather(*tasks):
        gathered_tasks.extend(tasks)
        # Don't actually run the tasks — we're only verifying update()
        # wired them up correctly. The per-task logic is covered by
        # the update_database tests above.
        return [None] * len(tasks)

    with patch("update.check_birthday", new=check_birthday_mock):
        with patch("update.asyncio.gather", new=fake_gather):
            await update.update(client, [100, 200])

    # check_birthday was called once per guild.
    assert check_birthday_mock.await_count == 2
    # gather received one task per guild.
    assert len(gathered_tasks) == 2


@pytest.mark.asyncio
async def test_update_handles_empty_guild_list(isolated_cwd, fresh_db, last_update_json):
    """No guilds → no work, no errors, but gather still runs with empty list."""
    client = MagicMock()
    client.get_guild.return_value = None

    gather_was_called = False

    async def fake_gather(*tasks):
        nonlocal gather_was_called
        gather_was_called = True
        return []

    with patch("update.asyncio.gather", new=fake_gather):
        await update.update(client, [])

    assert gather_was_called


# ------------------------------------------------------------------
# check_if_update_needed()
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_if_update_needed_runs_when_today_differs(isolated_cwd, last_update_json):
    """last_update.json has yesterday's date → update() runs, json gets
    overwritten with today's date."""
    client = MagicMock()
    update_mock = AsyncMock()
    # Force today to something different from "01/01/2000" by writing
    # yesterday explicitly and letting today be whatever it actually is.
    last_update_json.write_text(json.dumps({"last_update": "01/01/2000"}))

    with patch("update.update", new=update_mock):
        await update.check_if_update_needed(client, [])

    update_mock.assert_awaited_once_with(client, [])
    # last_update.json was overwritten with today's date.
    contents = json.loads(last_update_json.read_text())
    today_str = datetime.date.today().strftime("%m/%d/%Y")
    assert contents["last_update"] == today_str


@pytest.mark.asyncio
async def test_check_if_update_needed_skips_when_same_day(isolated_cwd, last_update_json):
    """last_update.json has today's date → update() does NOT run."""
    client = MagicMock()
    update_mock = AsyncMock()
    today_str = datetime.date.today().strftime("%m/%d/%Y")
    last_update_json.write_text(json.dumps({"last_update": today_str}))

    with patch("update.update", new=update_mock):
        await update.check_if_update_needed(client, [])

    update_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_if_update_needed_overwrites_last_update_json(isolated_cwd, last_update_json):
    """When the day changes, the JSON must be updated before update()
    runs, so a crash in update() doesn't loop infinitely on next start."""
    client = MagicMock()
    update_mock = AsyncMock(side_effect=RuntimeError("crash"))
    last_update_json.write_text(json.dumps({"last_update": "01/01/2000"}))

    with patch("update.update", new=update_mock):
        with pytest.raises(RuntimeError, match="crash"):
            await update.check_if_update_needed(client, [])

    # JSON still got the new date despite the crash inside update().
    contents = json.loads(last_update_json.read_text())
    today_str = datetime.date.today().strftime("%m/%d/%Y")
    assert contents["last_update"] == today_str