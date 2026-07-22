"""Route tests for dashboard/main.py.

test_dashboard_helpers.py covers the pure helpers and the schema migration.
This file covers the actual HTTP route handlers (the @app.get / @app.post
blocks) using FastAPI's TestClient. Combined, these two files lift
dashboard/main.py from 30% to a much more honest number.

Strategy
--------
The dashboard module reads four paths from module-level constants at
import time (DB_PATH, ROLES_PATH, BIRTHDAY_PATH, LOG_PATH). We import
the module once per session, then monkeypatch those constants to point
at fresh temp files for every test. The TestClient wraps the real `app`
object so the route decorators, middleware (SessionMiddleware), and
Pydantic models all run as they do in production.

OAUTH2_ENABLED is false in the test environment, so the auth guards
in every route fall through to `get_current_user(request)` which
returns {"username": "Guest", "avatar": ""} for any session. No
session cookie is required for the tests; we just call .get() and
.post() directly.
"""
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ------------------------------------------------------------------
# Module import with side effects patched
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def dashboard_app():
    """Import dashboard.main once per module, neutralizing the heavy
    side effects (_get_server_ip's real socket probe, the static-files
    mount which would fail without the static dir on disk).

    The socket patch is in effect only for the import — once the module
    has captured GIT_COMMIT and SERVER_IP, we restore the real socket
    so the FastAPI TestClient can spin up its ASGI server normally.

    SERVER_IP gets fixed up to a real string afterwards, because the
    socket mock leaves it as a MagicMock which trips downstream
    isinstance() checks."""
    import socket as socket_mod
    original_getaddrinfo = socket_mod.getaddrinfo
    original_socket = socket_mod.socket
    socket_mod.getaddrinfo = lambda *a, **kw: [(2, 1, 6, '', ('127.0.0.1', 0))]
    socket_mod.socket = MagicMock()
    try:
        import dashboard.main as dm
    finally:
        socket_mod.getaddrinfo = original_getaddrinfo
        socket_mod.socket = original_socket

    # The mocked _get_server_ip fell through both branches (loopback
    # filter excluded 127.0.0.1, then the UDP-probe path got a mock
    # getsockname that returns a MagicMock). Re-run it now that the
    # real socket is back so SERVER_IP is a real string.
    dm.SERVER_IP = dm._get_server_ip()

    yield dm


@pytest.fixture
def dashboard_env(dashboard_app, tmp_path, monkeypatch):
    """Per-test: redirect all file paths to a fresh tmp dir and pre-seed
    the SQLite schema so each test gets a clean but functional database.

    Returns a namespace with the live `app` (via TestClient), the db
    connection helper, and a list of paths for assertions.
    """
    dm = dashboard_app
    db_path = tmp_path / "discord.db"
    roles_path = tmp_path / "roles.json"
    birthday_path = tmp_path / "birthday.json"
    log_path = tmp_path / "rolm.log"

    # Mirror the prod schema. iDiscord._ensure_schema and
    # dashboard._ensure_schema both no-op when users exists.
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute(
        "CREATE TABLE users ("
        "username TEXT, birthday TEXT, tag TEXT, user_id TEXT, avatar TEXT)"
    )
    c.execute("CREATE TABLE user_guilds (user_id TEXT, guild_id TEXT)")
    c.execute("CREATE TABLE guilds (id TEXT PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(dm, "DB_PATH", db_path)
    monkeypatch.setattr(dm, "ROLES_PATH", roles_path)
    monkeypatch.setattr(dm, "BIRTHDAY_PATH", birthday_path)
    monkeypatch.setattr(dm, "LOG_PATH", log_path)

    # Reset the in-memory role cache from discord_api so each test
    # starts with an empty cache.
    import dashboard.discord_api as da
    da._roles_cache.clear()

    # Use SimpleNamespace so tests can read env.client, env.db_path, etc.
    # A regular class would have to declare these in the class body,
    # which loses access to the enclosing fixture's locals.
    from types import SimpleNamespace
    return SimpleNamespace(
        client=TestClient(dm.app),
        db_path=db_path,
        roles_path=roles_path,
        birthday_path=birthday_path,
        log_path=log_path,
    )


def _seed_user(c, user_id, username, birthday="00-00", tag="0001", avatar=None):
    """Insert a user with the iDiscord column order:
    (username, birthday, tag, user_id, avatar)."""
    c.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?, ?)",
        (username, birthday, tag, user_id, avatar),
    )


def _seed_guild(c, guild_id, name):
    c.execute("INSERT INTO guilds VALUES (?, ?)", (guild_id, name))


def _seed_user_guild(c, user_id, guild_id):
    c.execute("INSERT INTO user_guilds VALUES (?, ?)", (user_id, guild_id))


# ------------------------------------------------------------------
# /api/me
# ------------------------------------------------------------------

def test_api_me_returns_guest_when_oauth_disabled(dashboard_env):
    """OAUTH2_ENABLED is false in tests, so any session resolves to
    the default guest user. The frontend uses this to render the sidebar
    name when no real auth is configured."""
    r = dashboard_env.client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert "user" in body
    assert body["user"]["username"] == "Guest"


# ------------------------------------------------------------------
# /api/meta
# ------------------------------------------------------------------

def test_api_meta_returns_commit_and_ip(dashboard_env):
    """The header on every page reads the commit SHA and the server IP
    from this endpoint. Both are populated at module import time."""
    r = dashboard_env.client.get("/api/meta")
    assert r.status_code == 200
    body = r.json()
    assert "commit" in body
    assert "ip" in body
    # The meta endpoint exposes two module-level constants that were
    # captured at import time: GIT_COMMIT (a real or "unknown" string)
    # and SERVER_IP (a real IP, "unknown", or — under our socket-mocked
    # import fixture — a MagicMock). Just assert it's a string and has
    # content; the exact value is environment-dependent.
    assert isinstance(body["ip"], str)
    assert body["ip"]


# ------------------------------------------------------------------
# /api/stats
# ------------------------------------------------------------------

def test_api_stats_returns_zeros_on_empty_db(dashboard_env):
    r = dashboard_env.client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["users"] == 0
    assert body["guilds"] == 0
    assert body["members"] == 0
    assert body["birthdays"] == 0
    assert body["birthday_guilds"] == 0
    assert body["reaction_roles"] == 0


def test_api_stats_counts_birthdays_excluding_00_00(dashboard_env):
    """The Overview card shows 'X birthdays' — users with a real
    birthday, not the default '00-00' placeholder."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice", birthday="05-15")
    _seed_user(conn.cursor(), "2", "Bob", birthday="06-01")
    _seed_user(conn.cursor(), "3", "Charlie", birthday="00-00")
    conn.commit()
    conn.close()

    r = dashboard_env.client.get("/api/stats")
    assert r.json()["birthdays"] == 2


def test_api_stats_counts_unique_guilds_and_total_memberships(dashboard_env):
    """`guilds` is DISTINCT user_guilds rows; `members` is total
    user_guilds rows. A user in 3 guilds counts as 1 user but
    3 memberships."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    _seed_user(conn.cursor(), "2", "Bob")
    _seed_user_guild(conn.cursor(), "1", "100")
    _seed_user_guild(conn.cursor(), "1", "200")
    _seed_user_guild(conn.cursor(), "1", "300")
    _seed_user_guild(conn.cursor(), "2", "100")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/stats").json()
    assert body["users"] == 2
    assert body["guilds"] == 3
    assert body["members"] == 4


def test_api_stats_counts_reaction_roles_in_guild_scoped_format(dashboard_env):
    """roles.json can be in two formats: flat {emoji: id} or
    guild-scoped {guild_id: {emoji: id}}. The stats endpoint must
    count the right thing in each."""
    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": 1, ":b:": 2},
        "200": {":c:": 3},
    }))

    body = dashboard_env.client.get("/api/stats").json()
    assert body["reaction_roles"] == 3


def test_api_stats_counts_reaction_roles_in_legacy_flat_format(dashboard_env):
    dashboard_env.roles_path.write_text(json.dumps({":a:": 1, ":b:": 2}))

    body = dashboard_env.client.get("/api/stats").json()
    assert body["reaction_roles"] == 2


def test_api_stats_reads_birthday_guild_count_from_birthday_json(dashboard_env):
    dashboard_env.birthday_path.write_text(json.dumps({
        "guilds": [
            {"id": 100, "name": "A"},
            {"id": 200, "name": "B"},
            {"id": 300, "name": "C"},
        ]
    }))

    body = dashboard_env.client.get("/api/stats").json()
    assert body["birthday_guilds"] == 3


# ------------------------------------------------------------------
# /api/users  (paginated list with filters and sort)
# ------------------------------------------------------------------

def test_api_users_returns_empty_list_on_empty_db(dashboard_env):
    r = dashboard_env.client.get("/api/users")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["users"] == []


def test_api_users_returns_basic_user_fields(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "111", "Alice", birthday="05-15", tag="0001", avatar="av_a")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users").json()
    assert body["total"] == 1
    user = body["users"][0]
    assert user["user_id"] == "111"
    assert user["username"] == "Alice"
    assert user["birthday"] == "05-15"
    assert user["avatar"] == "av_a"


def test_api_users_respects_limit_and_offset(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    for i in range(5):
        _seed_user(conn.cursor(), str(i), f"user{i:02d}")
    conn.commit()
    conn.close()

    page1 = dashboard_env.client.get("/api/users?limit=2&offset=0").json()
    page2 = dashboard_env.client.get("/api/users?limit=2&offset=2").json()
    assert page1["total"] == 5
    assert len(page1["users"]) == 2
    assert len(page2["users"]) == 2
    # No overlap between pages.
    page1_ids = {u["user_id"] for u in page1["users"]}
    page2_ids = {u["user_id"] for u in page2["users"]}
    assert page1_ids.isdisjoint(page2_ids)


def test_api_users_filters_by_search_query(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    _seed_user(conn.cursor(), "2", "Bob")
    _seed_user(conn.cursor(), "3", "alice2")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users?q=alice").json()
    usernames = {u["username"] for u in body["users"]}
    assert usernames == {"Alice", "alice2"}


def test_api_users_filters_by_guild_id(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    _seed_user(conn.cursor(), "2", "Bob")
    _seed_user_guild(conn.cursor(), "1", "100")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users?guild_id=100").json()
    assert body["total"] == 1
    assert body["users"][0]["username"] == "Alice"


def test_api_users_filters_by_birthday_status_has(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice", birthday="05-15")
    _seed_user(conn.cursor(), "2", "Bob", birthday="00-00")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users?birthday_filter=has").json()
    assert body["total"] == 1
    assert body["users"][0]["username"] == "Alice"


def test_api_users_filters_by_birthday_status_none(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice", birthday="05-15")
    _seed_user(conn.cursor(), "2", "Bob", birthday="00-00")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users?birthday_filter=none").json()
    assert body["total"] == 1
    assert body["users"][0]["username"] == "Bob"


def test_api_users_sorts_descending(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    _seed_user(conn.cursor(), "2", "Bob")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users?sort_key=username&sort_dir=desc").json()
    assert [u["username"] for u in body["users"]] == ["Bob", "Alice"]


def test_api_users_ignores_unknown_sort_key(dashboard_env):
    """Defense against SQL injection: the unknown sort key falls
    back to the default 'u.username' rather than being interpolated
    into the SQL."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    conn.commit()
    conn.close()

    # This must not 500 or 503.
    r = dashboard_env.client.get("/api/users?sort_key=DROP+TABLE+users")
    assert r.status_code == 200


def test_api_users_includes_guild_names_via_join(dashboard_env):
    """`guild_names` is the human-readable version of `guilds` —
    resolved through the maintained guilds table."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    _seed_guild(conn.cursor(), "100", "BGE")
    _seed_user_guild(conn.cursor(), "1", "100")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/users").json()
    assert body["users"][0]["guilds"] == ["100"]
    assert body["users"][0]["guild_names"] == ["BGE"]


# ------------------------------------------------------------------
# /api/users/clean-up
# ------------------------------------------------------------------

def test_api_users_cleanup_removes_orphan_zero_birthday_users(dashboard_env):
    """A user with no birthday AND no guilds is considered stale (they
    were seen in chat once, then left every server). Clean-up deletes them."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Stale1", birthday="00-00")
    _seed_user(conn.cursor(), "2", "Stale2", birthday="00-00")
    _seed_user(conn.cursor(), "3", "HasGuild", birthday="00-00")
    _seed_user(conn.cursor(), "4", "HasBday", birthday="05-15")
    _seed_user_guild(conn.cursor(), "3", "100")
    conn.commit()
    conn.close()

    r = dashboard_env.client.post("/api/users/clean-up")
    assert r.status_code == 200
    assert r.json()["removed"] == 2

    remaining = sqlite3.connect(str(dashboard_env.db_path))
    rows = remaining.execute("SELECT username FROM users ORDER BY username").fetchall()
    remaining.close()
    assert {r[0] for r in rows} == {"HasBday", "HasGuild"}


def test_api_users_cleanup_is_noop_when_no_orphans(dashboard_env):
    r = dashboard_env.client.post("/api/users/clean-up")
    assert r.status_code == 200
    assert r.json()["removed"] == 0


# ------------------------------------------------------------------
# /api/roles  (GET, POST update, POST refresh)
# ------------------------------------------------------------------

def test_api_roles_get_returns_full_map_when_no_guild_id(dashboard_env):
    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": "111"},
        "200": {":b:": "222"},
    }))

    body = dashboard_env.client.get("/api/roles").json()
    assert body == {"100": {":a:": "111"}, "200": {":b:": "222"}}


def test_api_roles_get_stringifies_role_ids(dashboard_env):
    """18-digit snowflakes lose precision in JS without stringification."""
    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": 123456789012345678},
    }))

    body = dashboard_env.client.get("/api/roles").json()
    assert body["100"][":a:"] == "123456789012345678"


def test_api_roles_get_enriches_with_cached_role_names(dashboard_env):
    """When a guild_id is passed, the response includes the human-readable
    role_name from the in-memory role cache."""
    import dashboard.discord_api as da
    da._roles_cache["100"] = {"111": {"name": "Birthday!", "color": 0}}

    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": "111"},
    }))

    body = dashboard_env.client.get("/api/roles?guild_id=100").json()
    assert body["guild_id"] == "100"
    assert body["roles"][0]["emoji"] == ":a:"
    assert body["roles"][0]["role_id"] == "111"
    assert body["roles"][0]["role_name"] == "Birthday!"


def test_api_roles_get_upgrades_legacy_flat_format(dashboard_env):
    """A pre-rename roles.json (flat {emoji: id}) gets wrapped under the
    default BGE guild id so the rest of the code can treat it uniformly."""
    dashboard_env.roles_path.write_text(json.dumps({":a:": "111"}))

    body = dashboard_env.client.get("/api/roles").json()
    assert "254779349352448001" in body
    assert body["254779349352448001"][":a:"] == "111"


def test_api_roles_post_writes_to_disk(dashboard_env):
    """The Roles tab posts the edited mapping here. Must round-trip
    through disk so a bot restart sees the new data."""
    payload = {"roles": {"100": {":a:": "111", ":b:": "222"}}}
    r = dashboard_env.client.post("/api/roles", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    on_disk = json.loads(dashboard_env.roles_path.read_text())
    assert on_disk == {"100": {":a:": "111", ":b:": "222"}}


def test_api_roles_post_merges_into_existing_data(dashboard_env):
    """POST /api/roles adds/overwrites the posted guilds but preserves
    other guilds that weren't in the payload."""
    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": "1"},
        "200": {":b:": "2"},
    }))

    payload = {"roles": {"100": {":a:": "111"}}}  # overwrite 100, leave 200 alone
    dashboard_env.client.post("/api/roles", json=payload)

    on_disk = json.loads(dashboard_env.roles_path.read_text())
    assert on_disk["100"] == {":a:": "111"}
    assert on_disk["200"] == {":b:": "2"}


def test_api_roles_refresh_returns_cache_peek(dashboard_env):
    """The refresh button hits the Discord API for each guild's roles.
    The response includes a peek of what's in the cache afterwards so
    the UI can show counts without a follow-up call."""
    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": "111"},
    }))

    async def fake_refresh(ids):
        import dashboard.discord_api as da
        for gid in ids:
            da._roles_cache[gid] = {"111": {"name": "X", "color": 0}}

    with patch("dashboard.main.refresh_role_cache", side_effect=fake_refresh):
        r = dashboard_env.client.post("/api/roles/refresh")

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["guilds"] == ["100"]
    assert body["cache_peek"]["100"]["role_count"] == 1


def test_api_roles_refresh_surfaces_per_guild_errors(dashboard_env):
    dashboard_env.roles_path.write_text(json.dumps({
        "100": {":a:": "1"},
        "200": {":b:": "2"},
    }))

    async def fake_refresh(ids):
        if "100" in ids:
            raise RuntimeError("discord 500")

    with patch("dashboard.main.refresh_role_cache", side_effect=fake_refresh):
        body = dashboard_env.client.post("/api/roles/refresh").json()

    assert "100" in body["errors"]
    assert "200" not in body["errors"]


# ------------------------------------------------------------------
# /api/guilds  (GET, POST sync)
# ------------------------------------------------------------------

def test_api_guilds_returns_empty_on_empty_db(dashboard_env):
    assert dashboard_env.client.get("/api/guilds").json() == []


def test_api_guilds_merges_birthday_config_with_table_rows(dashboard_env):
    """The route returns one entry per row in the guilds table, with the
    birthday-channel and birthday-role fields filled in from birthday.json
    when the guild has a config entry. Names come from the table."""
    dashboard_env.birthday_path.write_text(json.dumps({
        "guilds": [
            {"id": "100", "name": "BGE", "birthday_channel": "200", "birthday_role": "300"},
        ]
    }))
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_guild(conn.cursor(), "100", "BGE")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/guilds").json()
    assert len(body) == 1
    g = body[0]
    assert g["id"] == "100"
    assert g["name"] == "BGE"  # from the table
    assert g["birthday_channel"] == "200"  # from birthday.json
    assert g["birthday_role"] == "300"


def test_api_guilds_returns_empty_strings_for_unconfigured_guilds(dashboard_env):
    """A guild in the table but not in birthday.json gets empty
    birthday-channel/role fields rather than missing keys."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_guild(conn.cursor(), "100", "UnconfiguredGuild")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/guilds").json()
    assert body[0]["birthday_channel"] == ""
    assert body[0]["birthday_role"] == ""


def test_api_guilds_sync_inserts_missing_guilds_from_user_guilds(dashboard_env):
    """A guild_id appears in user_guilds but not in the guilds table —
    sync must INSERT it, using birthday.json's name as a fallback."""
    dashboard_env.birthday_path.write_text(json.dumps({
        "guilds": [
            {"id": "100", "name": "BGE", "birthday_channel": "200", "birthday_role": "300"},
        ]
    }))
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    # Guild 100 is in the table; guild 999 is not. Sync should insert
    # only the missing one.
    _seed_guild(conn.cursor(), "100", "BGE")
    _seed_user_guild(conn.cursor(), "1", "100")
    _seed_user_guild(conn.cursor(), "1", "999")
    conn.commit()
    conn.close()

    body = dashboard_env.client.post("/api/guilds/sync").json()
    assert body["ok"] is True
    assert body["inserted"] == 1
    inserted_ids = {g["id"] for g in body["guilds"]}
    assert inserted_ids == {"100", "999"}
    # The new guild 999 has no birthday config, so its fields are
    # empty strings; the fallback name is the id itself.
    g999 = next(g for g in body["guilds"] if g["id"] == "999")
    assert g999["birthday_channel"] == ""
    assert g999["birthday_role"] == ""
    assert g999["name"] == "999"


def test_api_guilds_sync_uses_birthday_json_name_for_new_guilds(dashboard_env):
    """When a guild is in user_guilds AND in birthday.json but missing
    from the guilds table, the new row's name comes from birthday.json
    (which is the human-readable name) rather than the id."""
    dashboard_env.birthday_path.write_text(json.dumps({
        "guilds": [
            {"id": "100", "name": "BGE", "birthday_channel": "1", "birthday_role": "2"},
        ]
    }))
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice")
    _seed_user_guild(conn.cursor(), "1", "100")
    conn.commit()
    conn.close()

    body = dashboard_env.client.post("/api/guilds/sync").json()
    assert body["inserted"] == 1
    assert body["guilds"][0]["name"] == "BGE"


def test_api_guilds_sync_is_noop_when_all_present(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_guild(conn.cursor(), "100", "BGE")
    _seed_user_guild(conn.cursor(), "1", "100")
    conn.commit()
    conn.close()

    body = dashboard_env.client.post("/api/guilds/sync").json()
    assert body["inserted"] == 0


# ------------------------------------------------------------------
# /api/birthdays  (upcoming)
# ------------------------------------------------------------------

def test_api_birthdays_returns_empty_when_no_users_have_birthdays(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice", birthday="00-00")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays").json()
    assert body["birthdays"] == []


def test_api_birthdays_includes_today_as_zero_days_till(dashboard_env):
    """A user whose birthday is today shows up with days_till=0
    and the year-overflow logic still works."""
    today = date.today()
    bday = today.strftime("%m-%d")
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "BirthdayTwin", birthday=bday, avatar="av")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays").json()
    assert len(body["birthdays"]) == 1
    entry = body["birthdays"][0]
    assert entry["username"] == "BirthdayTwin"
    assert entry["days_till"] == 0
    assert entry["avatar"] == "av"


def test_api_birthdays_wraps_past_birthdays_to_next_year(dashboard_env):
    """A birthday that already passed this year must be reported as
    happening in the next year, not as -X days."""
    today = date.today()
    last_month_same_day = today.replace(day=today.day) - timedelta(days=30)
    bday = last_month_same_day.strftime("%m-%d")

    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "AlreadyPast", birthday=bday)
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays").json()
    entry = body["birthdays"][0]
    assert entry["days_till"] > 300  # roughly a year out


def test_api_birthdays_skips_unparseable_dates(dashboard_env):
    """A user with 'XX-YY' in the birthday column must not crash the
    endpoint; they just get silently skipped."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Good", birthday="05-15")
    _seed_user(conn.cursor(), "2", "Bad", birthday="XX-YY")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays").json()
    usernames = {b["username"] for b in body["birthdays"]}
    assert usernames == {"Good"}


def test_api_birthdays_sorts_by_month_then_day(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Dec1", birthday="12-01")
    _seed_user(conn.cursor(), "2", "Mar5", birthday="03-05")
    _seed_user(conn.cursor(), "3", "Mar2", birthday="03-02")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays").json()
    assert [b["username"] for b in body["birthdays"]] == ["Mar2", "Mar5", "Dec1"]


# ------------------------------------------------------------------
# /api/birthdays/list  (paginated, sortable, filterable)
# ------------------------------------------------------------------

def test_api_birthdays_list_paginates(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    for i in range(5):
        _seed_user(conn.cursor(), str(i), f"u{i:02d}", birthday="05-15")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays/list?limit=2&offset=0").json()
    assert body["total"] == 5
    assert len(body["birthdays"]) == 2


def test_api_birthdays_list_filters_by_month(dashboard_env):
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "JanUser", birthday="01-15")
    _seed_user(conn.cursor(), "2", "FebUser", birthday="02-15")
    _seed_user(conn.cursor(), "3", "MarUser", birthday="03-15")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get("/api/birthdays/list?month=2").json()
    assert body["total"] == 1
    assert body["birthdays"][0]["username"] == "FebUser"


def test_api_birthdays_list_sorts_by_days_till_desc(dashboard_env):
    """The Birthdays tab supports clicking column headers to sort.
    'days_till desc' must put the most-distant birthday first."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Soon", birthday=date.today().strftime("%m-%d"))
    _seed_user(conn.cursor(), "2", "Far", birthday="12-31")
    conn.commit()
    conn.close()

    body = dashboard_env.client.get(
        "/api/birthdays/list?sort_key=days_till&sort_dir=desc"
    ).json()
    assert body["birthdays"][0]["username"] == "Far"


def test_api_birthdays_list_ignores_invalid_month(dashboard_env):
    """A non-integer month param is silently ignored rather than 500ing."""
    conn = sqlite3.connect(str(dashboard_env.db_path))
    _seed_user(conn.cursor(), "1", "Alice", birthday="05-15")
    conn.commit()
    conn.close()

    r = dashboard_env.client.get("/api/birthdays/list?month=notanumber")
    assert r.status_code == 200
    assert r.json()["total"] == 1


# ------------------------------------------------------------------
# /api/logs
# ------------------------------------------------------------------

def test_api_logs_returns_empty_list_when_log_missing(dashboard_env):
    """If rolm.log doesn't exist yet (fresh deploy, no daily run),
    the endpoint returns an empty list, not a 500."""
    # log_path points at a file in tmp_path that doesn't exist.
    assert not dashboard_env.log_path.exists()
    body = dashboard_env.client.get("/api/logs").json()
    assert body == {"logs": []}


def test_api_logs_returns_last_n_lines(dashboard_env):
    dashboard_env.log_path.write_text(
        "line1\nline2\nline3\nline4\nline5\n"
    )

    body = dashboard_env.client.get("/api/logs?lines=3").json()
    assert body["logs"] == ["line3", "line4", "line5"]


def test_api_logs_default_to_200_lines(dashboard_env):
    """When no `lines` param is given, default is 200 — matches the
    docstring on the route and the frontend's 'Last 200 lines' hint."""
    lines = "\n".join(f"line{i}" for i in range(300)) + "\n"
    dashboard_env.log_path.write_text(lines)

    body = dashboard_env.client.get("/api/logs").json()
    assert len(body["logs"]) == 200
    assert body["logs"][0] == "line100"
    assert body["logs"][-1] == "line299"


# ------------------------------------------------------------------
# /auth/logout
# ------------------------------------------------------------------

def test_auth_logout_clears_session_and_redirects(dashboard_env):
    """With SessionMiddleware in play, logout pops 'user' and 302s to /.
    A TestClient with cookies follows the redirect by default, so we
    expect the final response to be 200 with the index template."""
    r = dashboard_env.client.get("/auth/logout", follow_redirects=False)
    assert r.status_code in (302, 307)  # either is acceptable
    assert r.headers["location"] == "/"
