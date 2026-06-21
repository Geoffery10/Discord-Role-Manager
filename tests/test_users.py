import pytest
import datetime
from users import User


@pytest.fixture
def user():
    return User("1234", "testuser", "01-01", "1")


# ------------------------------------------------------------------
# Existing tests (kept verbatim — behavior pinning)
# ------------------------------------------------------------------

def test_get_user_id(user):
    assert user.get_user_id() == "1234"


def test_get_username(user):
    assert user.get_username() == "testuser"


def test_get_birthday(user):
    assert user.get_birthday() == "01-01"


def test_get_birthday_datetime(user):
    assert user.get_birthday_datetime().strftime("%m-%d") == "01-01"


def test_get_birthday_date(user):
    assert user.get_birthday_date().strftime("%m-%d") == "01-01"


def test_get_tag(user):
    assert user.get_tag() == "1"


def test_set_user_id(user):
    user.set_user_id("5678")
    assert user.get_user_id() == "5678"


def test_set_username(user):
    user.set_username("newuser")
    assert user.get_username() == "newuser"


def test_set_birthday(user):
    user.set_birthday("02-02")
    assert user.get_birthday() == "02-02"


def test_set_birthday_datetime(user):
    user.set_birthday(datetime.datetime(2022, 2, 2))
    assert user.get_birthday() == "02-02"


def test_set_birthday_invalid(user):
    with pytest.raises(ValueError):
        user.set_birthday("2022-02-02")


def test_set_birthday_00_00(user):
    user.set_birthday("00-00")
    assert user.get_birthday() == "00-00"


def test_set_tag(user):
    user.set_tag("2")
    assert user.get_tag() == "2"


# ------------------------------------------------------------------
# New tests — close the remaining 93% gap
# ------------------------------------------------------------------

def test_get_birthday_datetime_returns_none_for_00_00(user):
    """A user with the unset '00-00' sentinel must return None from
    get_birthday_datetime, not raise or return a junk date."""
    user.set_birthday("00-00")
    assert user.get_birthday_datetime() is None


def test_get_birthday_date_returns_none_for_00_00(user):
    """Same as above for get_birthday_date (the .date() variant)."""
    user.set_birthday("00-00")
    assert user.get_birthday_date() is None


def test_set_birthday_rejects_non_string_non_datetime(user):
    """Passing an int, float, or None must raise ValueError with the
    documented message, not silently coerce or store junk."""
    with pytest.raises(ValueError, match="Invalid birthday format"):
        user.set_birthday(12345)  # int
    with pytest.raises(ValueError, match="Invalid birthday format"):
        user.set_birthday(None)   # None
    with pytest.raises(ValueError, match="Invalid birthday format"):
        user.set_birthday(3.14)   # float


def test_get_avatar_returns_none_by_default():
    """Constructor without an avatar argument defaults to None."""
    u = User("1234", "testuser")
    assert u.get_avatar() is None


def test_set_and_get_avatar_roundtrip(user):
    """set_avatar / get_avatar roundtrip stores and returns the same value."""
    user.set_avatar("avatar_hash_abc123")
    assert user.get_avatar() == "avatar_hash_abc123"


def test_set_avatar_to_none(user):
    """set_avatar(None) must be accepted (used when a member clears
    their avatar or has no custom one)."""
    user.set_avatar("old_hash")
    user.set_avatar(None)
    assert user.get_avatar() is None


def test_init_accepts_avatar_kwarg():
    """Constructor passes avatar through to set_avatar."""
    u = User("1234", "testuser", "01-01", "1", "initial_avatar")
    assert u.get_avatar() == "initial_avatar"


def test_init_accepts_avatar_none_explicitly():
    """Explicit avatar=None is the same as omitting the argument."""
    u = User("1234", "testuser", "01-01", "1", None)
    assert u.get_avatar() is None

