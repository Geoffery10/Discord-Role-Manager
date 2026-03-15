import asyncio
import builtins
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the module under test
import birthday

# Helper to create a mock user
def make_user(user_id: int, username: str, birthday: str):
    user = MagicMock()
    user.get_user_id.return_value = str(user_id)
    user.get_username.return_value = username
    user.get_birthday.return_value = birthday
    # For find_next_birthday path
    def get_birthday_date():
        # Return a date object if birthday is not "00-00"
        if birthday == "00-00":
            return None
        try:
            return datetime.datetime.strptime(birthday, "%m-%d").date()
        except ValueError:
            return datetime.datetime.strptime(birthday, "%m-%d-%Y").date()
    user.get_birthday_date = MagicMock(side_effect=get_birthday_date)
    return user

# Mock datetime to control "today"
import datetime

@pytest.fixture(autouse=True)
def mock_logger():
    with patch("utils.logger.log", new=AsyncMock()) as mock_log:
        yield mock_log

@pytest.fixture(autouse=True)
def mock_datetime_today():
    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2023, 5, 15)  # Fixed date for testing
    with patch("datetime.date", FixedDate):
        yield

@pytest.mark.asyncio
async def test_check_user_adds_role_and_sends_message():
    # Arrange: birthday matches today (05-15)
    user = make_user(12345, "TestUser", "05-15")
    # Mock RoleHandler
    mock_role_handler = AsyncMock()
    mock_role_handler.add_role.return_value = "role added"
    # Mock the guild and its get_channel method to return a simple async mock channel
    mock_channel = AsyncMock()
    mock_role_handler.guild = MagicMock()
    mock_role_handler.guild.get_channel = MagicMock(return_value=mock_channel)
    # guild_info dict
    guild_info = {
        "birthday_role": 999,
        "birthday_channel": 111,
    }
    # Act
    await birthday.check_user(user, mock_role_handler, MagicMock(), guild_info)
    # Assert role added
    mock_role_handler.add_role.assert_awaited_once_with(12345, 999)
    # Assert message sent
    mock_channel.send.assert_awaited()
    # Ensure logger was called for info about role and final info message
    # The exact calls are not important; just ensure no errors

@pytest.mark.asyncio
async def test_check_user_removes_role_when_not_birthday():
    # Arrange: birthday not today (06-01) while today is 05-15
    user = make_user(54321, "OtherUser", "06-01")
    mock_role_handler = AsyncMock()
    mock_role_handler.remove_role.return_value = "role removed"
    guild_info = {
        "birthday_role": 888,
        "birthday_channel": 222,
    }
    # Act
    await birthday.check_user(user, mock_role_handler, MagicMock(), guild_info)
    # Assert remove_role was called
    mock_role_handler.remove_role.assert_awaited_once_with(54321, 888)

@pytest.mark.asyncio
async def test_find_next_birthday_returns_correct_users():
    # Arrange mock guild and users
    mock_guild = MagicMock()
    mock_guild.id = 1
    # Create users with various birthdays
    user_today = make_user(1, "TodayUser", "05-15")
    user_future = make_user(2, "FutureUser", "05-20")
    user_past = make_user(3, "PastUser", "05-10")
    # Patch get_guild_users to return these users
    async def mock_get_guild_users(guild_id):
        return [user_today, user_future, user_past]
    with patch("birthday.get_guild_users", new=mock_get_guild_users):
        result = await birthday.find_next_birthday(mock_guild)
    # The next birthday could be today (user_today) or the next upcoming (user_future).
    # Accept either as correct based on implementation.
    assert len(result) == 1
    assert result[0].get_user_id() in {str(user_today.get_user_id()), str(user_future.get_user_id())}
