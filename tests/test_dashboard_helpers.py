"""Tests for dashboard/main.py — covers the pure helpers and the
schema migration.

dashboard/main.py has 530 stmts of route handlers (covered by Phase 11)
plus a small set of importable pure helpers. We test those here:

  _ensure_schema()      — same migration logic as iDiscord._ensure_schema
  _get_git_commit()     — subprocess wrapper
  _get_server_ip()      — socket wrapper
  db_conn()             — sqlite3 connection with busy_timeout
  read_json()           — pathlib wrapper
  write_json()          — pathlib wrapper

Importing dashboard.main has heavy side effects (FastAPI app build,
subprocess git call, socket probe). We patch the network-y bits
before importing.
"""
import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ------------------------------------------------------------------
# Module import with side effects patched
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def dashboard_main():
    """Import dashboard.main once per module with side effects neutralized."""
    import socket as socket_mod
    # Use monkeypatch-style context to undo after the module finishes.
    original_getaddrinfo = socket_mod.getaddrinfo
    original_socket = socket_mod.socket

    # Avoid real network calls during _get_server_ip()
    socket_mod.getaddrinfo = lambda *a, **kw: [(2, 1, 6, '', ('127.0.0.1', 0))]
    socket_mod.socket = MagicMock()

    try:
        import dashboard.main as dm
        yield dm
    finally:
        socket_mod.getaddrinfo = original_getaddrinfo
        socket_mod.socket = original_socket


# ------------------------------------------------------------------
# db_conn()
# ------------------------------------------------------------------

def test_db_conn_returns_sqlite_connection(dashboard_main):
    conn = dashboard_main.db_conn()
    try:
        assert isinstance(conn, sqlite3.Connection)
        # PRAGMA busy_timeout was set to 5000.
        c = conn.cursor()
        c.execute("PRAGMA busy_timeout")
        assert c.fetchone()[0] == 5000
    finally:
        conn.close()


# ------------------------------------------------------------------
# read_json() / write_json()
# ------------------------------------------------------------------

def test_read_json_returns_empty_dict_when_missing(dashboard_main, tmp_path):
    # Missing file → {} (not None, not raise).
    assert dashboard_main.read_json(tmp_path / "missing.json") == {}


def test_read_json_parses_existing_file(dashboard_main, tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({"guilds": ["100", "200"]}))
    assert dashboard_main.read_json(path) == {"guilds": ["100", "200"]}


def test_write_json_creates_file_with_indent_4(dashboard_main, tmp_path):
    path = tmp_path / "out.json"
    dashboard_main.write_json(path, {"hello": "world", "n": 1})
    contents = path.read_text()
    # Indent of 4 means each level has 4 spaces.
    assert "    \"hello\"" in contents
    assert json.loads(contents) == {"hello": "world", "n": 1}


def test_write_json_overwrites_existing(dashboard_main, tmp_path):
    path = tmp_path / "out.json"
    path.write_text(json.dumps({"old": True}))
    dashboard_main.write_json(path, {"new": True})
    assert json.loads(path.read_text()) == {"new": True}


# ------------------------------------------------------------------
# _get_git_commit()
# ------------------------------------------------------------------

def test_get_git_commit_returns_short_sha(dashboard_main):
    with patch("subprocess.check_output") as mock_co:
        mock_co.return_value = "abc1234\n"
        assert dashboard_main._get_git_commit() == "abc1234"


def test_get_git_commit_returns_unknown_on_subprocess_error(dashboard_main):
    # If git isn't available or the dir isn't a repo, return "unknown"
    # rather than raising — the dashboard must still render.
    with patch("subprocess.check_output", side_effect=FileNotFoundError("no git")):
        assert dashboard_main._get_git_commit() == "unknown"


# ------------------------------------------------------------------
# _get_server_ip()
# ------------------------------------------------------------------

def test_get_server_ip_filters_loopback_and_ipv6(dashboard_main):
    # When getaddrinfo returns a mix of loopback, IPv6, and IPv4, the
    # filter must keep only non-loopback IPv4 addresses.
    import socket as socket_mod
    fake_addrs = [
        (2, 1, 6, '', ('127.0.0.1', 0)),    # IPv4 loopback — skip
        (2, 1, 6, '', ('::1', 0, 0, 0)),    # IPv6 — skip
        (2, 1, 6, '', ('192.168.1.42', 0)),  # IPv4 — keep
    ]
    with patch.object(socket_mod, "getaddrinfo", return_value=fake_addrs):
        ip = dashboard_main._get_server_ip()
    assert "192.168.1.42" in ip
    assert "127.0.0.1" not in ip
    assert "::1" not in ip


def test_get_server_ip_falls_back_to_udp_probe(dashboard_main):
    # getaddrinfo returns only loopback → fall through to the UDP probe.
    import socket as socket_mod
    with patch.object(socket_mod, "getaddrinfo", return_value=[
        (2, 1, 6, '', ('127.0.0.1', 0)),
    ]):
        fake_sock = MagicMock()
        fake_sock.getsockname.return_value = ["10.0.0.5"]
        with patch.object(socket_mod, "socket", return_value=fake_sock):
            ip = dashboard_main._get_server_ip()
    assert ip == "10.0.0.5"


def test_get_server_ip_returns_unknown_when_both_fail(dashboard_main):
    # Everything fails → "unknown" sentinel, no exception.
    import socket as socket_mod
    with patch.object(socket_mod, "getaddrinfo", side_effect=OSError("nope")):
        with patch.object(socket_mod, "socket", side_effect=OSError("nope")):
            assert dashboard_main._get_server_ip() == "unknown"


# ------------------------------------------------------------------
# _ensure_schema()
# ------------------------------------------------------------------

def test_ensure_schema_noop_when_users_table_missing(dashboard_main, tmp_path, monkeypatch):
    # On a fresh DB with no users table, the migration is a no-op.
    db = tmp_path / "discord.db"
    monkeypatch.setattr(dashboard_main, "DB_PATH", db)
    dashboard_main._ensure_schema()
    conn = sqlite3.connect(str(db))
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert c.fetchone() is None
    conn.close()


def test_ensure_schema_adds_avatar_column_when_missing(dashboard_main, tmp_path, monkeypatch):
    # Legacy users table (no avatar column) gets the avatar column added.
    db = tmp_path / "discord.db"
    conn = sqlite3.connect(str(db))
    c = conn.cursor()
    c.execute(
        "CREATE TABLE users ("
        "username TEXT, birthday TEXT, tag TEXT, user_id TEXT)"
    )
    c.execute("CREATE TABLE user_guilds (user_id TEXT, guild_id TEXT)")
    c.execute("CREATE TABLE guilds (id TEXT, name TEXT)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(dashboard_main, "DB_PATH", db)
    dashboard_main._ensure_schema()

    conn = sqlite3.connect(str(db))
    c = conn.cursor()
    c.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in c.fetchall()}
    assert "avatar" in cols
    conn.close()


def test_ensure_schema_rebuilds_guilds_pk(dashboard_main, tmp_path, monkeypatch):
    # Legacy guilds table (no PK, with duplicate ids) gets rebuilt with
    # id as PRIMARY KEY and dedupes via MIN(name).
    db = tmp_path / "discord.db"
    conn = sqlite3.connect(str(db))
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

    monkeypatch.setattr(dashboard_main, "DB_PATH", db)
    dashboard_main._ensure_schema()

    conn = sqlite3.connect(str(db))
    c = conn.cursor()
    c.execute("PRAGMA table_info(guilds)")
    pk_cols = [row[1] for row in c.fetchall() if row[5]]
    assert pk_cols == ["id"]
    c.execute("SELECT id, name FROM guilds WHERE id = ?", ("42",))
    rows = c.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "First"  # MIN('First', 'Second')
    conn.close()