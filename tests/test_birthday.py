import asyncio
import builtins  # noqa: F401  (kept for backward-compat with potential monkey-patches)
import datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
import birthday


# ------------------------------------------------------------------
# Test helpers
# ------------------------------------------------------------------

def make_user(user_id, username, bday, roles=None):
    """Build a MagicMock that quacks like a users.User.

    `bday` accepts both "MM-DD" and "MM-DD-YYYY" formats; the
    get_birthday_date() side effect handles either, returning None for
    the "00-00" unset sentinel so find_next_birthday can skip it.
    """
    user = MagicMock()
    user.get_user_id.return_value = str(user_id)
    user.get_username.return_value = username
    user.get_birthday.return_value = bday

    def get_birthday_date():
        if bday == "00-00":
            return None
        for fmt in ("%m-%d", "%m-%d-%Y"):
            try:
                return datetime.datetime.strptime(bday, fmt).date()
            except ValueError:
                continue
        return None

    user.get_birthday_date.side_effect = get_birthday_date
    # Some tests inspect get_birthday_datetime — provide the same logic.
    user.get_birthday_datetime.side_effect = get_birthday_date
    return user


# ------------------------------------------------------------------
# Module-level state for the fixed-today patcher.
# We patch datetime.date with a subclass whose today() reads from this
# module-level holder, so tests can flip it via the fixed_today_ctx fixture.
# ------------------------------------------------------------------

_FIXED_TODAY = (2023, 5, 15)


class _FixedDate(datetime.date):
    @classmethod
    def today(cls):
        return cls(*_FIXED_TODAY)


@pytest.fixture(autouse=True)
def mock_logger():
    """Replace utils.logger.log with an AsyncMock for every test.

    Patch both the canonical location (utils.logger.log) AND the
    already-resolved reference in birthday's module globals — birthday
    does `from utils.logger import log` which binds the symbol at
    import time, so patching utils.logger.log alone won't affect it.
    """
    mock = AsyncMock()
    with patch("utils.logger.log", new=mock):
        with patch("birthday.log", new=mock):
            yield mock


@pytest.fixture
def fixed_today_ctx():
    """Yield a callable(year, month, day) that returns a context manager.
    Each test enters one to control 'today' for the duration of the block.

    Example:
        def test_x(fixed_today_ctx):
            with fixed_today_ctx(2024, 12, 31):
                ...  # datetime.date.today() returns 2024-12-31 here
    """
    class _Ctx:
        def __init__(self, year, month, day):
            self.year, self.month, self.day = year, month, day

        def __enter__(self):
            global _FIXED_TODAY
            _FIXED_TODAY = (self.year, self.month, self.day)
            self._p = patch("datetime.date", _FixedDate)
            self._p.start()
            return self

        def __exit__(self, *exc):
            self._p.stop()
            return False

    def _make(year, month, day):
        return _Ctx(year, month, day)

    yield _make


# ------------------------------------------------------------------
# check_user() — 00-00 early return and YYYY-MM-DD fallback
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_user_returns_silently_on_00_00(fixed_today_ctx, mock_logger):
    """A user with '00-00' (unset) birthday must short-circuit and never
    touch the role handler or send any messages."""
    user = make_user(12345, "Unset", "00-00")
    role_handler = AsyncMock()
    guild_info = {"birthday_role": 999, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    role_handler.add_role.assert_not_called()
    role_handler.remove_role.assert_not_called()


@pytest.mark.asyncio
async def test_check_user_accepts_yyyy_format_birthday(fixed_today_ctx):
    """Birthdays stored as 'MM-DD-YYYY' must still trigger the happy path."""
    user = make_user(12345, "BornIn1990", "05-15-1990")
    role_handler = AsyncMock()
    role_handler.add_role.return_value = "added"
    channel = AsyncMock()
    role_handler.guild = MagicMock()
    role_handler.guild.get_channel = MagicMock(return_value=channel)
    guild_info = {"birthday_role": 999, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    role_handler.add_role.assert_awaited_once_with(12345, 999)
    channel.send.assert_awaited()


@pytest.mark.asyncio
async def test_check_user_skips_role_when_role_id_is_minus_one(fixed_today_ctx):
    """birthday_role == -1 disables role add/remove; the channel send
    still happens on the birthday."""
    user = make_user(12345, "Alice", "05-15")
    role_handler = AsyncMock()
    channel = AsyncMock()
    role_handler.guild = MagicMock()
    role_handler.guild.get_channel = MagicMock(return_value=channel)
    guild_info = {"birthday_role": -1, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    role_handler.add_role.assert_not_called()
    role_handler.remove_role.assert_not_called()
    channel.send.assert_awaited()


@pytest.mark.asyncio
async def test_check_user_swallows_add_role_exception(fixed_today_ctx, mock_logger):
    """If role_handler.add_role raises, the user get_role lookup failed
    or the API call exploded — check_user must not crash; it should log
    and continue to the message-send step."""
    user = make_user(12345, "Alice", "05-15")
    role_handler = AsyncMock()
    role_handler.add_role.side_effect = RuntimeError("discord 500")
    channel = AsyncMock()
    role_handler.guild = MagicMock()
    role_handler.guild.get_channel = MagicMock(return_value=channel)
    guild_info = {"birthday_role": 999, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        # Should not raise.
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    # Message still got sent — the exception didn't break the flow.
    channel.send.assert_awaited()


@pytest.mark.asyncio
async def test_check_user_returns_when_get_channel_raises(fixed_today_ctx, mock_logger):
    """If role_handler.guild.get_channel raises (bad config?), bail out
    before trying to send — don't blow up the daily loop."""
    user = make_user(12345, "Alice", "05-15")
    role_handler = AsyncMock()
    role_handler.add_role.return_value = "added"
    role_handler.guild = MagicMock()
    role_handler.guild.get_channel = MagicMock(side_effect=RuntimeError("no channel"))
    guild_info = {"birthday_role": 999, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        # Should not raise.
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    role_handler.add_role.assert_awaited_once_with(12345, 999)


@pytest.mark.asyncio
async def test_check_user_returns_when_send_raises(fixed_today_ctx, mock_logger):
    """If the channel.send call fails (e.g. deleted channel), swallow it."""
    user = make_user(12345, "Alice", "05-15")
    role_handler = AsyncMock()
    role_handler.add_role.return_value = "added"
    channel = AsyncMock()
    channel.send.side_effect = RuntimeError("missing permissions")
    role_handler.guild = MagicMock()
    role_handler.guild.get_channel = MagicMock(return_value=channel)
    guild_info = {"birthday_role": 999, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        # Should not raise.
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    role_handler.add_role.assert_awaited_once_with(12345, 999)


# ------------------------------------------------------------------
# find_next_birthday()
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_next_birthday_returns_empty_list_when_no_users(fixed_today_ctx):
    guild = MagicMock()
    guild.id = 1
    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.get_guild_users", new=AsyncMock(return_value=[])):
            result = await birthday.find_next_birthday(guild)
    assert result == []


@pytest.mark.asyncio
async def test_find_next_birthday_skips_users_with_00_00(fixed_today_ctx):
    """Users with the '00-00' unset sentinel must not influence the result."""
    today_user = make_user(1, "Today", "05-15")
    unset = make_user(2, "Unset", "00-00")
    guild = MagicMock()
    guild.id = 1

    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.get_guild_users",
                   new=AsyncMock(return_value=[today_user, unset])):
            result = await birthday.find_next_birthday(guild)

    assert len(result) == 1
    assert result[0].get_user_id() == "1"


@pytest.mark.asyncio
async def test_find_next_birthday_includes_all_users_on_same_upcoming_date(fixed_today_ctx):
    """Multiple users sharing the next upcoming birthday all come back."""
    u1 = make_user(1, "Alice", "05-20")
    u2 = make_user(2, "Bob", "05-20")
    u3 = make_user(3, "Carol", "06-30")  # further out
    guild = MagicMock()
    guild.id = 1

    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.get_guild_users",
                   new=AsyncMock(return_value=[u1, u2, u3])):
            result = await birthday.find_next_birthday(guild)

    assert len(result) == 2
    ids = sorted(u.get_user_id() for u in result)
    assert ids == ["1", "2"]


@pytest.mark.asyncio
async def test_find_next_birthday_wraps_to_next_year_for_january(fixed_today_ctx):
    """A user with a January birthday found in December must wrap to next year."""
    future_user = make_user(1, "FutureUser", "05-20")  # 5 days out, but in next year
    jan_user = make_user(2, "JanuaryUser", "01-15")     # ~26 days out, earlier
    guild = MagicMock()
    guild.id = 1

    with fixed_today_ctx(2023, 12, 20):
        with patch("birthday.get_guild_users",
                   new=AsyncMock(return_value=[future_user, jan_user])):
            result = await birthday.find_next_birthday(guild)

    assert len(result) == 1
    assert result[0].get_user_id() == "2"


@pytest.mark.asyncio
async def test_find_next_birthday_today_is_treated_as_upcoming(fixed_today_ctx):
    """Today's birthday must be picked as the next birthday (not 'past')."""
    today_user = make_user(1, "BirthdayKid", "05-15")
    future_user = make_user(2, "FutureUser", "05-20")
    guild = MagicMock()
    guild.id = 1

    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.get_guild_users",
                   new=AsyncMock(return_value=[today_user, future_user])):
            result = await birthday.find_next_birthday(guild)

    assert len(result) == 1
    assert result[0].get_user_id() == "1"


# ------------------------------------------------------------------
# check_birthday() — the orchestrator (regression coverage for the
# line 57 truthiness fix)
# ------------------------------------------------------------------

def _last_call_user(mock_check_user):
    """Pull the first positional arg (the user) from the most recent
    await call on a mocked check_user."""
    call = mock_check_user.await_args
    assert call is not None, "check_user was never awaited"
    args = call.args
    assert args, "check_user was called without positional args"
    return args[0]


@pytest.mark.asyncio
async def test_check_birthday_loads_json_and_calls_check_user_per_member(
    isolated_cwd, fresh_db, birthday_json, fixed_today_ctx, mock_logger
):
    """End-to-end of the orchestrator:
      1. Loads birthday.json
      2. Filters users by guild membership (guild.get_member)
      3. Iterates each user and calls check_user

    This is the regression for the line-57 truthiness bug — if 'if not
    users is None' ever comes back, the per-user loop silently no-ops
    and no one's birthday ever gets processed.
    """
    import iDiscord
    # Seed two users; one will be in the guild, one won't.
    await iDiscord.add_user("111", "Alice", "05-15", "0001", None)
    await iDiscord.add_user("222", "Bob", "05-15", "0002", None)

    guild = MagicMock()
    guild.id = 100
    guild.name = "Test Guild"
    # Alice (111) is in the guild; Bob (222) is not.
    alice_member = MagicMock()

    def _get_member(uid):
        return alice_member if str(uid) == "111" else None

    guild.get_member = MagicMock(side_effect=_get_member)

    # Patch RoleHandler so we don't try to construct against a real discord Guild.
    fake_role_handler = MagicMock()
    fake_role_handler.guild = guild
    fake_role_handler.guild.get_channel = MagicMock(return_value=AsyncMock())

    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.RoleHandler", return_value=fake_role_handler):
            with patch("birthday.check_user", new=AsyncMock()) as check_user_mock:
                await birthday.check_birthday(guild)

    # Only Alice (the guild member) gets a check_user call.
    check_user_mock.assert_awaited_once()
    user_arg = _last_call_user(check_user_mock)
    assert user_arg.get_user_id() == "111"


@pytest.mark.asyncio
async def test_check_birthday_returns_on_birthday_json_load_error(
    isolated_cwd, fresh_db, no_birthday_json, fixed_today_ctx, mock_logger
):
    """If birthday.json is missing/unreadable, the orchestrator must log
    the error and return — not crash the daily task loop."""
    import iDiscord
    await iDiscord.add_user("111", "Alice", "05-15", "0001", None)

    guild = MagicMock()
    guild.id = 100
    # no_birthday_json fixture guarantees birthday.json is absent.

    # Should not raise.
    await birthday.check_birthday(guild)

    # The error log must have been called at least once with the 'error' type.
    error_calls = [c for c in mock_logger.await_args_list
                   if c.kwargs.get("type") == "error" or
                   (len(c.args) > 0 and c.args[0] == "error")]
    assert error_calls, "expected an error log when birthday.json is missing"


@pytest.mark.asyncio
async def test_check_birthday_warns_when_guild_not_in_json(
    isolated_cwd, fresh_db, birthday_json, fixed_today_ctx, mock_logger
):
    """birthday.json is present but doesn't contain this guild's id —
    the orchestrator must warn and bail."""
    import iDiscord
    await iDiscord.add_user("111", "Alice", "05-15", "0001", None)

    guild = MagicMock()
    guild.id = 999  # not in birthday_json (which has 100, 200)
    guild.name = "Unknown Guild"

    await birthday.check_birthday(guild)

    warning_calls = [c for c in mock_logger.await_args_list
                     if c.kwargs.get("type") == "warning" or
                     (len(c.args) > 0 and c.args[0] == "warning")]
    assert warning_calls, "expected a warning log when guild is not in birthday.json"


@pytest.mark.asyncio
async def test_check_birthday_filters_users_not_in_guild(
    isolated_cwd, fresh_db, birthday_json, fixed_today_ctx, mock_logger
):
    """Two users in DB, only one in the guild — only the in-guild user
    is passed to check_user. This is the same filter as the happy-path
    test above but isolates it for clarity."""
    import iDiscord
    await iDiscord.add_user("111", "Alice", "05-15", "0001", None)
    await iDiscord.add_user("222", "Bob", "05-15", "0002", None)

    guild = MagicMock()
    guild.id = 100
    guild.name = "Test Guild"
    # Neither user is in the guild.
    guild.get_member = MagicMock(return_value=None)

    fake_role_handler = MagicMock()
    fake_role_handler.guild = guild
    fake_role_handler.guild.get_channel = MagicMock(return_value=AsyncMock())

    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.RoleHandler", return_value=fake_role_handler):
            with patch("birthday.check_user", new=AsyncMock()) as check_user_mock:
                await birthday.check_birthday(guild)

    check_user_mock.assert_not_called()


# ------------------------------------------------------------------
# Existing tests (kept verbatim for behavior pinning)
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_user_adds_role_and_sends_message(fixed_today_ctx):
    """Birthday matches today (05-15) → add role + send message."""
    user = make_user(12345, "TestUser", "05-15")
    mock_role_handler = AsyncMock()
    mock_role_handler.add_role.return_value = "role added"
    mock_channel = AsyncMock()
    mock_role_handler.guild = MagicMock()
    mock_role_handler.guild.get_channel = MagicMock(return_value=mock_channel)
    guild_info = {"birthday_role": 999, "birthday_channel": 111}

    with fixed_today_ctx(2023, 5, 15):
        await birthday.check_user(user, mock_role_handler, MagicMock(), guild_info)

    mock_role_handler.add_role.assert_awaited_once_with(12345, 999)
    mock_channel.send.assert_awaited()


@pytest.mark.asyncio
async def test_check_user_swallows_remove_role_exception_on_non_birthday(fixed_today_ctx, mock_logger):
    """When removing the birthday role (user not on birthday today),
    if remove_role raises, log the error and continue."""
    user = make_user(54321, "OtherUser", "06-01")
    role_handler = AsyncMock()
    role_handler.remove_role.side_effect = RuntimeError("discord 500")
    guild_info = {"birthday_role": 888, "birthday_channel": 222}

    with fixed_today_ctx(2023, 5, 15):
        # Should not raise.
        await birthday.check_user(user, role_handler, MagicMock(), guild_info)

    role_handler.remove_role.assert_awaited_once_with(54321, 888)
    # Error log was called.
    error_calls = [c for c in mock_logger.await_args_list
                   if c.kwargs.get("type") == "error" or
                   (len(c.args) > 0 and c.args[0] == "error")]
    assert error_calls, "expected an error log when remove_role raises"


@pytest.mark.asyncio
async def test_check_user_removes_role_when_not_birthday(fixed_today_ctx):
    """Birthday does not match today → remove role."""
    user = make_user(54321, "OtherUser", "06-01")
    mock_role_handler = AsyncMock()
    mock_role_handler.remove_role.return_value = "role removed"
    guild_info = {"birthday_role": 888, "birthday_channel": 222}

    with fixed_today_ctx(2023, 5, 15):
        await birthday.check_user(user, mock_role_handler, MagicMock(), guild_info)

    mock_role_handler.remove_role.assert_awaited_once_with(54321, 888)


@pytest.mark.asyncio
async def test_find_next_birthday_returns_correct_users(fixed_today_ctx):
    """Sanity check on find_next_birthday's basic selection logic."""
    mock_guild = MagicMock()
    mock_guild.id = 1
    user_today = make_user(1, "TodayUser", "05-15")
    user_future = make_user(2, "FutureUser", "05-20")
    user_past = make_user(3, "PastUser", "05-10")

    async def mock_get_guild_users(guild_id):
        return [user_today, user_future, user_past]

    with fixed_today_ctx(2023, 5, 15):
        with patch("birthday.get_guild_users", new=mock_get_guild_users):
            result = await birthday.find_next_birthday(mock_guild)

    assert len(result) == 1
    assert result[0].get_user_id() in {str(user_today.get_user_id()),
                                       str(user_future.get_user_id())}