"""Tests for main.py — covers the two pure helpers that don't need
a live discord.py gateway: load_roles() and flatten_roles().

main.py has many other entry points (MyClient event handlers, slash
commands) but they all run inside an active discord.Client connection.
Testing them properly would require asyncio + discord test scaffolding
that's out of scope for this phase.

Importing main.py has side effects: it reads roles.json at module
scope and calls client.run(TOKEN) at the bottom. We patch
discord.Client.run to a no-op before importing, and provide a
roles.json fixture so the module-level load_roles() call doesn't
crash.
"""
import json
from unittest.mock import patch

import pytest


@pytest.fixture
def roles_json(tmp_path):
    """Write a default roles.json into a tmp dir and chdir there.

    Returns the parsed data dict. Tears down the file on exit.
    """
    data = {
        "254779349352448001": {
            ":trap:763101905244389376": "796516467222511626",
            ":confused_anime:557426389180088340": "796516551364050975",
        },
        "786690956514426910": {
            ":drink_anime:557426135001202708": "796516609862139934",
        },
    }
    path = tmp_path / "roles.json"
    path.write_text(json.dumps(data))

    original_cwd = None
    import os
    original_cwd = os.getcwd()
    os.chdir(str(tmp_path))
    try:
        yield data, path
    finally:
        os.chdir(original_cwd)


@pytest.fixture
def import_main(roles_json, monkeypatch):
    """Import main.py with discord.Client.run patched to a no-op.

    main.py calls client.run(TOKEN) at module scope which would try to
    actually start a discord gateway. We patch it out so the module
    can be imported in a test environment.
    """
    monkeypatch.setattr("discord.Client.run", lambda self, *a, **kw: None)
    import main
    return main


# ------------------------------------------------------------------
# flatten_roles()
# ------------------------------------------------------------------

def test_flatten_roles_flattens_nested_dict(import_main):
    # Guild-scoped {guild_id: {emoji: role_id}} → flat {emoji: role_id}
    roles = {
        "100": {":emoji_a:": 1, ":emoji_b:": 2},
        "200": {":emoji_c:": 3},
    }
    flat = import_main.flatten_roles(roles)
    assert flat == {":emoji_a:": 1, ":emoji_b:": 2, ":emoji_c:": 3}


def test_flatten_roles_converts_string_role_ids_to_int(import_main):
    # When role_ids come from JSON they arrive as strings; flatten_roles
    # is the one place that coerces them to int for use as discord IDs.
    roles = {"100": {":emoji_a:": "12345"}}
    flat = import_main.flatten_roles(roles)
    assert flat == {":emoji_a:": 12345}
    assert isinstance(flat[":emoji_a:"], int)


def test_flatten_roles_passes_through_int_role_ids(import_main):
    # If a caller passes ints directly (e.g. tests, in-memory builds),
    # flatten_roles must not re-coerce them — that would be a no-op for
    # ints but would still pass the isinstance check.
    roles = {"100": {":emoji_a:": 12345}}
    flat = import_main.flatten_roles(roles)
    assert flat == {":emoji_a:": 12345}


def test_flatten_roles_handles_empty_dict(import_main):
    # An empty input dict must produce an empty output, not raise.
    assert import_main.flatten_roles({}) == {}


def test_flatten_roles_keeps_last_value_on_emoji_collision(import_main):
    # If two guilds happen to define the same emoji key (unusual but
    # possible after merging configs), the later one wins. This pins
    # the documented behavior so a future refactor doesn't silently
    # change it.
    roles = {
        "100": {":emoji_dup:": 1},
        "200": {":emoji_dup:": 2},
    }
    flat = import_main.flatten_roles(roles)
    assert flat == {":emoji_dup:": 2}


# ------------------------------------------------------------------
# load_roles()
# ------------------------------------------------------------------

def test_load_roles_reads_guild_scoped_format(import_main, roles_json):
    # Default roles.json is {guild_id: {emoji: role_id}} and load_roles
    # returns it as-is when all top-level values are dicts.
    data, _ = roles_json
    loaded = import_main.load_roles("roles.json")
    assert loaded == data


def test_load_roles_upgrades_flat_format_to_guild_scoped(import_main, tmp_path):
    # Older configs are flat {emoji: role_id}. load_roles must wrap them
    # under the canonical main guild id (254779349352448001) so the
    # downstream code can treat both formats uniformly.
    flat_data = {":emoji_legacy:": "12345"}
    legacy_path = tmp_path / "legacy_roles.json"
    legacy_path.write_text(json.dumps(flat_data))

    loaded = import_main.load_roles(str(legacy_path))
    assert loaded == {"254779349352448001": flat_data}


def test_load_roles_takes_custom_path(import_main, tmp_path):
    # load_roles accepts a path arg; verify it doesn't always read
    # "roles.json" implicitly.
    custom_data = {"999": {":custom:": "54321"}}
    custom_path = tmp_path / "custom_roles.json"
    custom_path.write_text(json.dumps(custom_data))

    loaded = import_main.load_roles(str(custom_path))
    assert loaded == custom_data