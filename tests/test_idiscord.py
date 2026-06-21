"""Tests for iDiscord.py — the SQLite data access layer.

iDiscord.py exposes async functions that read/write three tables:
users, user_guilds, and guilds. The column order in the users table
(per the live DB and per add_user's INSERT statement) is:
    (username, birthday, tag, user_id, avatar)

These tests use the isolated_cwd and fresh_db fixtures from conftest.py.
Each test starts with empty tables; populate as needed inside the test.
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import os  # noqa: E402  (placed here so other imports stay grouped)


# Imports happen inside tests where needed so that conftest fixtures have
# already chdir'd into the isolated tmp dir. test_birthday.py already
# imports birthday (which imports iDiscord) at module scope — keep things
# consistent here by importing iDiscord lazily inside tests.

def _open_iDiscord():
    """Import iDiscord fresh from the current cwd."""
    import iDiscord
    return iDiscord


# ------------------------------------------------------------------
# Schema migration (_ensure_schema)
# ------------------------------------------------------------------

def test_ensure_schema_noop_when_users_table_missing(reload_idiscord_in):
    """On a fresh DB with no users table, _ensure_schema is a no-op."""
    with reload_idiscord_in("fresh") as workdir:
        idisc = _open_iDiscord()
        db_path = Path(str(workdir)) / "discord.db"
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        # users table should still not exist.
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        assert c.fetchone() is None
        # guilds and user_guilds also don't get created — schema only migrates
        # existing structure, never creates tables from scratch.
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='guilds'")
        assert c.fetchone() is None
        conn.close()


def test_ensure_schema_adds_avatar_column_when_missing(reload_idiscord_in):
    """Legacy users table (no avatar column) gets the avatar column added."""
    with reload_idiscord_in("legacy") as workdir:
        idisc = _open_iDiscord()
        db_path = Path(str(workdir)) / "discord.db"
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("PRAGMA table_info(users)")
        cols = {row[1] for row in c.fetchall()}
        assert "avatar" in cols
        conn.close()


def test_ensure_schema_is_noop_when_avatar_present(reload_idiscord_in):
    """If avatar column already exists, _ensure_schema doesn't error or duplicate it."""
    with reload_idiscord_in("current") as workdir:
        idisc = _open_iDiscord()
        db_path = Path(str(workdir)) / "discord.db"
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("PRAGMA table_info(users)")
        avatar_rows = [row for row in c.fetchall() if row[1] == "avatar"]
        assert len(avatar_rows) == 1
        conn.close()


def test_ensure_schema_rebuilds_guilds_pk_when_missing(reload_idiscord_in):
    """Legacy guilds table (no PK) gets rebuilt with id as PRIMARY KEY,
    collapsing duplicate ids via MIN(name) into guilds_new."""
    # First build the legacy dir + seed duplicate ids, then trigger the
    # migration. We do this manually because the helper reloads iDiscord
    # immediately after creating the schema — there's no hook to inject
    # seed data between creation and reload.
    import importlib
    import tempfile
    import iDiscord as _idisc

    workdir = Path(tempfile.mkdtemp(prefix="rolm_pk_"))
    db_path = workdir / "discord.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute(
        "CREATE TABLE users ("
        "username TEXT, birthday TEXT, tag TEXT, user_id TEXT)"
    )
    c.execute("CREATE TABLE user_guilds (user_id TEXT, guild_id TEXT)")
    c.execute("CREATE TABLE guilds (id TEXT, name TEXT)")
    c.execute("INSERT INTO guilds VALUES (?, ?)", ("42", "First"))
    c.execute("INSERT INTO guilds VALUES (?, ?)", ("42", "Second"))
    conn.commit()
    conn.close()

    original_cwd = os.getcwd()
    os.chdir(str(workdir))
    try:
        importlib.reload(_idisc)
        # Migration has now run. Verify PK + dedupe.
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("PRAGMA table_info(guilds)")
        pk_cols = [row[1] for row in c.fetchall() if row[5]]
        assert pk_cols == ["id"]
        c.execute("SELECT id, name FROM guilds WHERE id = ?", ("42",))
        rows = c.fetchall()
        assert len(rows) == 1
        # MIN('First', 'Second') == 'First'
        assert rows[0] == ("42", "First")
        conn.close()
    finally:
        os.chdir(original_cwd)


def test_ensure_schema_noop_when_guilds_pk_present(reload_idiscord_in):
    """If guilds.id is already PRIMARY KEY, _ensure_schema does nothing."""
    with reload_idiscord_in("current") as workdir:
        idisc = _open_iDiscord()
        db_path = Path(str(workdir)) / "discord.db"
        # Seed an extra row directly to prove it survives.
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("INSERT INTO guilds (id, name) VALUES (?, ?)", ("99", "Keep"))
        conn.commit()
        conn.close()
        # Re-trigger _ensure_schema by reloading.
        import importlib
        importlib.reload(idisc)
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("SELECT id, name FROM guilds WHERE id = ?", ("99",))
        assert c.fetchone() == ("99", "Keep")
        conn.close()


# ------------------------------------------------------------------
# connect()
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_returns_connection_and_cursor(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    conn, c = await idisc.connect()
    try:
        assert conn is not None
        assert c is not None
        # Cursor must be usable.
        c.execute("SELECT 1")
        assert c.fetchone() == (1,)
        # busy_timeout PRAGMA was set.
        c.execute("PRAGMA busy_timeout")
        assert c.fetchone()[0] == 5000
    finally:
        conn.close()


# ------------------------------------------------------------------
# get_users / get_user
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_users_returns_empty_list_when_table_empty(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    users = await idisc.get_users()
    assert users == []


@pytest.mark.asyncio
async def test_get_users_returns_user_objects_for_all_rows(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", "av_a")
    await idisc.add_user("u2", "bob", "06-30", "0002", None)

    users = await idisc.get_users()
    assert len(users) == 2
    by_id = {u.get_user_id(): u for u in users}
    assert by_id["u1"].get_username() == "alice"
    assert by_id["u1"].get_birthday() == "01-15"
    assert by_id["u1"].get_tag() == "0001"
    assert by_id["u1"].get_avatar() == "av_a"
    assert by_id["u2"].get_username() == "bob"
    assert by_id["u2"].get_avatar() is None


@pytest.mark.asyncio
async def test_get_user_returns_user_when_present(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", "av_a")
    user = await idisc.get_user("u1")
    assert user is not None
    assert user.get_username() == "alice"
    assert user.get_birthday() == "01-15"


@pytest.mark.asyncio
async def test_get_user_returns_none_when_absent(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    assert await idisc.get_user("nope") is None


# ------------------------------------------------------------------
# add_user
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_user_persists_row_with_defaults(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    user = await idisc.add_user("u1", "alice")
    assert user.get_user_id() == "u1"
    assert user.get_username() == "alice"
    # Defaults: birthday="00-00", tag="1", avatar=None
    assert user.get_birthday() == "00-00"
    assert user.get_tag() == "1"
    assert user.get_avatar() is None

    # Confirm it's actually in the DB.
    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_username() == "alice"


@pytest.mark.asyncio
async def test_add_user_persists_row_with_all_args(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    user = await idisc.add_user("u2", "bob", "06-30", "0002", "av_b")
    fetched = await idisc.get_user("u2")
    assert fetched is not None
    assert fetched.get_birthday() == "06-30"
    assert fetched.get_tag() == "0002"
    assert fetched.get_avatar() == "av_b"


# ------------------------------------------------------------------
# delete_user
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_user_removes_row(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice")
    await idisc.delete_user("u1")
    assert await idisc.get_user("u1") is None


@pytest.mark.asyncio
async def test_delete_user_is_noop_when_user_missing(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    # Should not raise — DELETE of nonexistent row is a no-op in SQLite.
    await idisc.delete_user("does-not-exist")
    assert await idisc.get_users() == []


# ------------------------------------------------------------------
# update_user
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_user_adds_when_missing(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    user = idisc.User("u1", "alice", "01-15", "0001", "av_a")
    await idisc.update_user(user_obj=user)

    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_birthday() == "01-15"
    assert fetched.get_avatar() == "av_a"


@pytest.mark.asyncio
async def test_update_user_updates_when_present(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", "old_avatar")
    user = idisc.User("u1", "alice2", "02-20", "0002", "new_avatar")
    await idisc.update_user(user_obj=user)

    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_username() == "alice2"
    assert fetched.get_birthday() == "02-20"
    assert fetched.get_tag() == "0002"
    assert fetched.get_avatar() == "new_avatar"


@pytest.mark.asyncio
async def test_update_user_accepts_kwargs_without_obj(isolated_cwd, fresh_db):
    """update_user() can be called with kwargs instead of a User object."""
    idisc = _open_iDiscord()
    await idisc.update_user(user_id="u1", username="alice", birthday="03-03", tag="0003", avatar="kwa")

    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_username() == "alice"
    assert fetched.get_birthday() == "03-03"
    assert fetched.get_tag() == "0003"
    assert fetched.get_avatar() == "kwa"


# ------------------------------------------------------------------
# Granular update_* helpers
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_user_avatar_writes_column(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", None)
    await idisc.update_user_avatar("u1", "hash_123")
    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_avatar() == "hash_123"


@pytest.mark.asyncio
async def test_update_user_tag_writes_column(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", None)
    await idisc.update_user_tag("u1", "9999")
    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_tag() == "9999"


@pytest.mark.asyncio
async def test_update_user_username_writes_column(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", None)
    await idisc.update_user_username("u1", "alice2")
    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_username() == "alice2"


@pytest.mark.asyncio
async def test_update_user_birthday_writes_column(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice", "01-15", "0001", None)
    await idisc.update_user_birthday("u1", "12-25")
    fetched = await idisc.get_user("u1")
    assert fetched is not None
    assert fetched.get_birthday() == "12-25"


# ------------------------------------------------------------------
# Guild membership
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_user_to_guild_inserts_row(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice")
    await idisc.add_user_to_guild("u1", "100")
    assert await idisc.is_user_in_guild("u1", "100") is True


@pytest.mark.asyncio
async def test_add_user_to_guild_is_idempotent(isolated_cwd, fresh_db):
    """Calling add_user_to_guild twice must not insert a duplicate row."""
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice")
    await idisc.add_user_to_guild("u1", "100")
    await idisc.add_user_to_guild("u1", "100")

    conn = sqlite3.connect("discord.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_guilds WHERE user_id = ? AND guild_id = ?", ("u1", "100"))
    assert c.fetchone()[0] == 1
    conn.close()


@pytest.mark.asyncio
async def test_remove_user_from_guild_deletes_row(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice")
    await idisc.add_user_to_guild("u1", "100")
    await idisc.remove_user_from_guild("u1", "100")
    assert await idisc.is_user_in_guild("u1", "100") is False


@pytest.mark.asyncio
async def test_is_user_in_guild_returns_false_when_absent(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    assert await idisc.is_user_in_guild("u1", "100") is False


@pytest.mark.asyncio
async def test_get_guild_users_returns_only_guild_members(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_user("u1", "alice")
    await idisc.add_user("u2", "bob")
    await idisc.add_user("u3", "carol")
    await idisc.add_user_to_guild("u1", "100")
    await idisc.add_user_to_guild("u3", "100")
    # u2 is NOT in guild 100.

    members = await idisc.get_guild_users("100")
    ids = sorted(u.get_user_id() for u in members)
    assert ids == ["u1", "u3"]


@pytest.mark.asyncio
async def test_get_guild_users_returns_empty_when_no_members(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    members = await idisc.get_guild_users("999")
    assert members == []


# ------------------------------------------------------------------
# Guilds table
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_guild_to_table_inserts_or_replaces(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_guild_to_table("100", "Test Guild")
    await idisc.add_guild_to_table("100", "Renamed Guild")  # INSERT OR REPLACE

    conn = sqlite3.connect("discord.db")
    c = conn.cursor()
    c.execute("SELECT name FROM guilds WHERE id = ?", ("100",))
    assert c.fetchone() == ("Renamed Guild",)
    conn.close()


@pytest.mark.asyncio
async def test_remove_guild_from_table_deletes(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()
    await idisc.add_guild_to_table("100", "Test Guild")
    await idisc.remove_guild_from_table("100")

    conn = sqlite3.connect("discord.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM guilds WHERE id = ?", ("100",))
    assert c.fetchone()[0] == 0
    conn.close()


@pytest.mark.asyncio
async def test_sync_guilds_table_inserts_all_client_guilds(isolated_cwd, fresh_db):
    idisc = _open_iDiscord()

    # Build a fake discord Client with two guilds.
    guild_a = MagicMock()
    guild_a.id = 100
    guild_a.name = "Alpha"
    guild_b = MagicMock()
    guild_b.id = 200
    guild_b.name = "Beta"

    client = MagicMock()
    client.guilds = [guild_a, guild_b]

    await idisc.sync_guilds_table(client)

    conn = sqlite3.connect("discord.db")
    c = conn.cursor()
    c.execute("SELECT id, name FROM guilds ORDER BY id")
    assert c.fetchall() == [("100", "Alpha"), ("200", "Beta")]
    conn.close()


@pytest.mark.asyncio
async def test_sync_guilds_table_upserts_existing(isolated_cwd, fresh_db):
    """Running sync twice with a renamed guild must update the row, not duplicate."""
    idisc = _open_iDiscord()

    guild = MagicMock()
    guild.id = 100
    guild.name = "Original"

    client = MagicMock()
    client.guilds = [guild]

    await idisc.sync_guilds_table(client)

    guild.name = "Renamed"
    await idisc.sync_guilds_table(client)

    conn = sqlite3.connect("discord.db")
    c = conn.cursor()
    c.execute("SELECT name FROM guilds WHERE id = ?", ("100",))
    assert c.fetchone() == ("Renamed",)
    c.execute("SELECT COUNT(*) FROM guilds WHERE id = ?", ("100",))
    assert c.fetchone()[0] == 1
    conn.close()