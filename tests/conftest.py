"""Shared pytest fixtures for the Rolm test suite.

The biggest constraint this conftest works around: the production modules
hardcode paths like sqlite3.connect('discord.db') and open('birthday.json')
relative to the current working directory. Importing birthday, update, or
iDiscord runs real I/O against whatever is in cwd.

The fix: chdir into an isolated temp directory for the whole test session
and pre-create the schema files there. Any module imported during tests
sees a clean, empty workspace and writes only to the tmp dir.
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest


# Session-wide tmp dir the entire test run lives in.
@pytest.fixture(scope="session")
def isolated_cwd(tmp_path_factory):
    """Create an isolated workspace and chdir into it for the session.

    Anything imported during tests (iDiscord, birthday, update, etc.) will
    open files relative to this directory.
    """
    tmp = tmp_path_factory.mktemp("rolm_test")
    original = os.getcwd()
    os.chdir(tmp)

    # Pre-create the SQLite schema so the module-level _ensure_schema() call
    # in iDiscord.py is a no-op (users table already exists, avatar column
    # already present, guilds.id already a PK). Without this, importing
    # iDiscord in a session that hasn't run the migration yet would still
    # touch the tmp DB, which is fine — but mirroring the prod schema here
    # means tests don't all pay the migration cost on every import.
    db_path = tmp / "discord.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    # Column order MUST match what iDiscord.add_user() writes:
    # (username, birthday, tag, user_id, avatar)
    c.execute(
        "CREATE TABLE users ("
        "username TEXT, birthday TEXT, tag TEXT, user_id TEXT, avatar TEXT)"
    )
    c.execute(
        "CREATE TABLE user_guilds (user_id TEXT, guild_id TEXT)"
    )
    c.execute(
        "CREATE TABLE guilds (id TEXT PRIMARY KEY, name TEXT)"
    )
    conn.commit()
    conn.close()

    yield tmp

    os.chdir(original)


# -------------------------
# iDiscord fixtures
# -------------------------

@pytest.fixture
def fresh_db(isolated_cwd):
    """Empty the iDiscord tables before a test, leave schema intact.

    iDiscord holds no persistent connection between calls — each function
    opens and closes its own. So wiping the rows is sufficient; no need
    to reload the module.
    """
    db_path = Path(str(isolated_cwd)) / "discord.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM user_guilds")
    c.execute("DELETE FROM guilds")
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def reload_idiscord_in(tmp_path):
    """Yield a context manager that chdirs into a tmp dir, then re-imports
    iDiscord so its module-level _ensure_schema() runs against that dir's
    freshly-built DB.

    Usage:
        def test_x(reload_idiscord_in):
            with reload_idiscord_in(schema="legacy") as workdir:
                # iDiscord._ensure_schema() has already run against workdir
                ...
    """
    import importlib

    class _Ctx:
        def __init__(self, workdir, restore_to):
            self.workdir = workdir
            self._restore_to = restore_to

        def __enter__(self):
            return self.workdir

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self._restore_to)

    class _Helper:
        def __call__(self, schema):
            workdir = tmp_path / f"idiscord_{schema}"
            workdir.mkdir(exist_ok=True)
            db_path = workdir / "discord.db"
            conn = sqlite3.connect(str(db_path))
            c = conn.cursor()
            if schema == "legacy":
                # No avatar column, guilds without PK.
                c.execute(
                    "CREATE TABLE users ("
                    "username TEXT, birthday TEXT, tag TEXT, user_id TEXT)"
                )
                c.execute("CREATE TABLE user_guilds (user_id TEXT, guild_id TEXT)")
                c.execute("CREATE TABLE guilds (id TEXT, name TEXT)")
            elif schema == "current":
                c.execute(
                    "CREATE TABLE users ("
                    "username TEXT, birthday TEXT, tag TEXT, user_id TEXT, avatar TEXT)"
                )
                c.execute("CREATE TABLE user_guilds (user_id TEXT, guild_id TEXT)")
                c.execute("CREATE TABLE guilds (id TEXT PRIMARY KEY, name TEXT)")
            elif schema == "fresh":
                # No users table at all.
                pass
            else:
                raise ValueError(f"unknown schema: {schema}")
            conn.commit()
            conn.close()

            restore_to = os.getcwd()
            os.chdir(str(workdir))
            import iDiscord
            importlib.reload(iDiscord)
            return _Ctx(workdir, restore_to)

    yield _Helper()


# -------------------------
# birthday.py / update.py fixtures
# -------------------------

@pytest.fixture
def birthday_json(isolated_cwd):
    """Write a birthday.json into the isolated cwd. Returns the parsed dict."""
    data = {
        "guilds": [
            {
                "id": "100",
                "name": "Test Guild",
                "birthday_role": 999,
                "birthday_channel": 111,
            },
            {
                "id": "200",
                "name": "Other Guild",
                "birthday_role": 888,
                "birthday_channel": 222,
            },
        ]
    }
    path = Path(str(isolated_cwd)) / "birthday.json"
    path.write_text(json.dumps(data))
    return data


@pytest.fixture
def last_update_json(isolated_cwd):
    """Write a last_update.json. Default value: yesterday (forces update).

    Override by writing to the path inside the test before invoking the
    function under test.
    """
    path = Path(str(isolated_cwd)) / "last_update.json"
    path.write_text(json.dumps({"last_update": "01/01/2000"}))
    return path