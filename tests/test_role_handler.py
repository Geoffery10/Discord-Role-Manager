"""Tests for role_handler.py — the Discord role add/remove wrapper.

RoleHandler wraps discord.Guild to provide add_role, remove_role, and
get_roles. The interesting behavior is in the failure paths: missing
role, missing member, role-not-in-member's-role-list. None of these
were exercised before this file existed.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from role_handler import RoleHandler


# ------------------------------------------------------------------
# Fake Discord primitives
# ------------------------------------------------------------------

def make_role(name="Birthday", role_id=999):
    """A sync-returned MagicMock standing in for a discord.Role."""
    role = MagicMock()
    role.id = role_id
    role.name = name
    # Used in the return-string f-string: f'Role {role} has been ...'
    role.__str__ = lambda self=name: name
    return role


def make_member(name="alice", user_id=12345, roles=None):
    """An async-fetched MagicMock standing in for a discord.Member.

    `roles` is a plain list (we never call Role-specific methods on it).
    """
    member = MagicMock()
    member.id = user_id
    member.name = name
    member.roles = list(roles) if roles is not None else []
    # add_roles / remove_roles are coroutines in real discord.py.
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


def make_guild(role=None, member=None):
    """Build a fake discord.Guild.

    get_role() is sync (returns the role mock or None).
    fetch_member() is async (returns the member mock or None).
    """
    guild = MagicMock()
    guild.get_role = MagicMock(return_value=role)
    guild.fetch_member = AsyncMock(return_value=member)
    return guild


# ------------------------------------------------------------------
# add_role
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_add_role_success_calls_add_roles_and_returns_message():
    role = make_role(name="Birthday", role_id=999)
    member = make_member(name="alice", user_id=12345)
    guild = make_guild(role=role, member=member)
    handler = RoleHandler(guild)

    msg = await handler.add_role(12345, 999)

    assert "Birthday" in msg
    assert "alice" in msg
    member.add_roles.assert_awaited_once_with(role)
    guild.fetch_member.assert_awaited_once_with(12345)
    guild.get_role.assert_called_once_with(999)


@pytest.mark.asyncio
async def test_add_role_returns_not_found_when_role_is_none():
    member = make_member()
    guild = make_guild(role=None, member=member)
    handler = RoleHandler(guild)

    msg = await handler.add_role(12345, 999)

    assert msg == "Role or member (12345) not found"
    member.add_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_add_role_returns_not_found_when_member_is_none():
    role = make_role()
    guild = make_guild(role=role, member=None)
    handler = RoleHandler(guild)

    msg = await handler.add_role(12345, 999)

    assert msg == "Role or member (12345) not found"
    role  # silence unused warnings
    guild.fetch_member.assert_awaited_once_with(12345)


@pytest.mark.asyncio
async def test_add_role_returns_not_found_when_both_none():
    guild = make_guild(role=None, member=None)
    handler = RoleHandler(guild)

    msg = await handler.add_role(12345, 999)

    assert msg == "Role or member (12345) not found"


# ------------------------------------------------------------------
# remove_role
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_remove_role_success_calls_remove_roles_when_member_has_role():
    role = make_role(name="Birthday", role_id=999)
    member = make_member(name="alice", user_id=12345, roles=[role])
    guild = make_guild(role=role, member=member)
    handler = RoleHandler(guild)

    msg = await handler.remove_role(12345, 999)

    assert "Birthday" in msg
    assert "alice" in msg
    member.remove_roles.assert_awaited_once_with(role)


@pytest.mark.asyncio
async def test_remove_role_returns_already_absent_message_when_role_not_in_member_roles():
    """Member exists but doesn't have the role — remove is a no-op + info message."""
    role = make_role(name="Birthday", role_id=999)
    other_role = make_role(name="Other", role_id=888)
    member = make_member(name="alice", user_id=12345, roles=[other_role])
    guild = make_guild(role=role, member=member)
    handler = RoleHandler(guild)

    msg = await handler.remove_role(12345, 999)

    assert "alice" in msg
    assert "Birthday" in msg
    # Critical: remove_roles must NOT be called when the member doesn't have it.
    member.remove_roles.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_role_returns_not_found_when_role_is_none():
    member = make_member()
    guild = make_guild(role=None, member=member)
    handler = RoleHandler(guild)

    msg = await handler.remove_role(12345, 999)

    assert msg == "Role or member (12345) not found"


@pytest.mark.asyncio
async def test_remove_role_returns_not_found_when_member_is_none():
    role = make_role()
    guild = make_guild(role=role, member=None)
    handler = RoleHandler(guild)

    msg = await handler.remove_role(12345, 999)

    assert msg == "Role or member (12345) not found"


# ------------------------------------------------------------------
# get_roles
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_roles_returns_member_roles_list():
    role_a = make_role(name="A", role_id=1)
    role_b = make_role(name="B", role_id=2)
    member = make_member(roles=[role_a, role_b])
    guild = make_guild(member=member)
    handler = RoleHandler(guild)

    roles = await handler.get_roles(12345, 999)

    assert roles == [role_a, role_b]
    guild.fetch_member.assert_awaited_once_with(12345)


@pytest.mark.asyncio
async def test_get_roles_returns_empty_list_when_member_is_none():
    guild = make_guild(member=None)
    handler = RoleHandler(guild)

    roles = await handler.get_roles(12345, 999)

    assert roles == []