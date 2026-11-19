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



# ------------------------------------------------------------------
# parse_month_day()
#
# CPython 3.15 rejects %d without a year directive (python/cpython#70647):
# strptime("05-15", "%m-%d") raises ValueError. Every stored birthday is
# yearless, so parsing has to go through an anchor year. These pin that, and
# the leap-day case the old implicit 1900 year could never express.
# ------------------------------------------------------------------

def test_parse_month_day_anchors_to_leap_year():
    from users import parse_month_day
    assert parse_month_day("05-15") == datetime.date(2000, 5, 15)


def test_parse_month_day_handles_leap_day():
    from users import parse_month_day
    assert parse_month_day("02-29") == datetime.date(2000, 2, 29)


def test_parse_month_day_accepts_legacy_year_form():
    from users import parse_month_day
    assert parse_month_day("05-15-1990") == datetime.date(1990, 5, 15)


def test_parse_month_day_rejects_year_first():
    from users import parse_month_day
    with pytest.raises(ValueError):
        parse_month_day("2022-02-02")


def test_parse_month_day_rejects_out_of_range_month():
    from users import parse_month_day
    with pytest.raises(ValueError):
        parse_month_day("13-01")


def test_no_module_parses_yearless_dates_with_strptime():
    """Guard: no source or test file may call strptime with a %d format
    that lacks %Y.

    That pattern is a hard error on 3.15, so a reintroduction must fail here
    rather than in CI or in the bot. Parsed with ast rather than by text
    matching so comments and docstrings mentioning the pattern don't count.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    paths = list(root.glob("*.py")) + list((root / "tests").glob("*.py"))
    offenders = []
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name != "strptime" or len(node.args) < 2:
                continue
            fmt = node.args[1]
            if (isinstance(fmt, ast.Constant) and isinstance(fmt.value, str)
                    and "%d" in fmt.value and "%Y" not in fmt.value):
                offenders.append(f"{path.name}:{node.lineno} {fmt.value!r}")
    assert not offenders, offenders


def test_user_get_birthday_date_handles_leap_day():
    u = User("1234", "leap", "02-29", "1")
    assert u.get_birthday_date() == datetime.date(2000, 2, 29)
