# User object that can store data found in the database
from datetime import datetime

class User:
    def __init__(self, user_id, username, birthday="00-00", tag="1"):
        self.set_user_id(user_id)
        self.set_username(username)
        self.set_birthday(birthday)
        self.set_tag(tag)

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
        return datetime.strptime(self._birthday, "%m-%d")
    
    def get_birthday_date(self):
        if self._birthday == "00-00":
            return None
        return datetime.strptime(self._birthday, "%m-%d").date()

    def get_tag(self):
        return self._tag

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
                    datetime.strptime(birthday, "%m-%d")
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
