import pytest
import datetime
from users import User

@pytest.fixture
def user():
    return User("1234", "testuser", "01-01", "1")

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

