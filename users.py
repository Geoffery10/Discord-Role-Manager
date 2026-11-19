# User object that can store data found in the database
from datetime import datetime

# Stored birthdays are yearless "MM-DD" (plus legacy "MM-DD-YYYY" rows).
# Parsing a yearless value needs an anchor year, because CPython 3.15 rejects
# %d without a year directive outright ("Day of month directive '%d' may not be
# used without a year directive", python/cpython#70647) and 3.13 only warns
# about it. The implicit year used to be 1900, which is not a leap year, so
# "02-29" could never parse at all. Anchor to a leap year so Feb 29 works.
_BIRTHDAY_ANCHOR_YEAR = 2000
_YEARLESS_FORMAT = "%Y-%m-%d"


def parse_month_day(value):
    """Parse a stored birthday into a datetime.date.

    Accepts "MM-DD" and the legacy "MM-DD-YYYY" form. Raises ValueError on
    anything else.
    """
    text = str(value).strip()
    if text.count("-") == 2:
        return datetime.strptime(text, "%m-%d-%Y").date()
    return datetime.strptime(f"{_BIRTHDAY_ANCHOR_YEAR}-{text}", _YEARLESS_FORMAT).date()


class User:
    def __init__(self, user_id, username, birthday="00-00", tag="1", avatar=None):
        self.set_user_id(user_id)
        self.set_username(username)
        self.set_birthday(birthday)
        self.set_tag(tag)
        self.set_avatar(avatar)

    # Getters
    def get_user_id(self):
        return self._user_id

    def get_username(self):
        return self._username

    def get_birthday(self):
        return self._birthday
    
    def get_birthday_datetime(self):
        if self._birthday == "00-00":
            return None
        parsed = parse_month_day(self._birthday)
        return datetime(parsed.year, parsed.month, parsed.day)
    
    def get_birthday_date(self):
        if self._birthday == "00-00":
            return None
        return parse_month_day(self._birthday)

    def get_tag(self):
        return self._tag

    def get_avatar(self):
        return self._avatar

    # Setters
    def set_user_id(self, user_id):
        self._user_id = user_id

    def set_username(self, username):
        self._username = username

    def set_birthday(self, birthday):
        if birthday == "00-00":
            self._birthday = birthday
        else:
            if isinstance(birthday, str):    
                try:
                    parse_month_day(birthday)
                except ValueError:
                    raise ValueError("Invalid birthday format. Please use a string in the format 'MM-DD' or a datetime object.")
                else:
                    self._birthday = birthday
            elif isinstance(birthday, datetime):
                self._birthday = birthday.strftime("%m-%d")
            else:
                raise ValueError("Invalid birthday format. Please use a string in the format 'MM-DD' or a datetime object.")

    def set_tag(self, tag):
        self._tag = tag

    def set_avatar(self, avatar):
        self._avatar = avatar
