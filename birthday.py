import json
import datetime
import random
import sqlite3
from iDiscord import get_guild_users
from role_handler import RoleHandler
from users import User

birthday_messages = [
    "Happy birthday @USER! Wishing you all the best on your special day.",
    "Sending birthday wishes to the one and only @USER! Have a great day filled with love and laughter.",
    "Happy birthday @USER! May your day be as amazing as you are.",
    "Happy birthday to the best @USER! Have a fantastic day and an even better year.",
    "Happy birthday @USER! Wishing you all the best on your special day and many more to come.",
    "Happy birthday, @USER! May all your dreams come true on your special day and always.",
    "Happy birthday @USER! Wishing you a day filled with joy and surrounded by the people you love.",
    "Happy birthday @USER! Wishing you all the best on your special day and a year filled with happiness."
]


# Check if it's a user's birthday using the discord.db database
async def check_birthday(guild):
    role_handler = RoleHandler(guild) 
    # Connect to the database
    conn = sqlite3.connect('discord.db')
    c = conn.cursor()
    
    # Get all the users_id, username, and birthday from the database
    c.execute("SELECT user_id, username, birthday FROM users")
    users = c.fetchall()
    c.close()

    # Check if the user has a birthday in the database
    for user in users:
        print(user)
        await check_user(user, role_handler)

    print("Checked all users")


async def check_user(user, role_handler):
    global birthday_messages
    # Get the user's birthday (format is MM-DD or MM-DD-YYYY in the database) using the birthday key
    if user[2] == "00-00":
        return
    try:
        birthday = datetime.datetime.strptime(user[2], "%m-%d").date()
    except ValueError:
        birthday = datetime.datetime.strptime(user[2], "%m-%d-%Y").date()
    
        

    # Get the current date
    today = datetime.date.today()

    # Check if it's the user's birthday
    if today.month == birthday.month and today.day == birthday.day:
        # Get the user's id
        user_id = user[0]

        # Get the birthday role id
        role_id = 961688424341987409
        try:
            message = await role_handler.add_role(user_id, role_id)
            print(message.encode('utf-8'))
            # Send a random birthday message to the general channel
            # Get the general channel by id from the guild
            general_channel = role_handler.guild.get_channel(254779349352448001)
            # Get a random birthday message
            message = random.choice(birthday_messages)
            # Replace the @USER tag with @mention for the user
            message = message.replace("@USER", f"<@{user_id}>")
            # Send the message to the general channel
            await general_channel.send(message)
        except Exception as e:
            print(f"Failed to add role to user {user_id}")
            print(f"Error: {e}")
    else:
        # Get the user's id
        user_id = user[0]

        # Get the birthday role id
        role_id = 961688424341987409
        try:
            message = await role_handler.remove_role(user_id, role_id)
            print(message.encode('utf-8'))
        except Exception as e:
            print(f"Failed to remove role from user {user_id}")
            print(f"Error: {e}")
    return

async def find_next_birthday(guild): 
    # Get users from guild 
    users = await get_guild_users(guild.id)

    # Get the current date
    today = datetime.date.today()

    # Get the next birthday
    next_birthday = None
    next_birthday_users = []
    for user in users:
        # Parse the user's birthday string into a date object
        birthday = user.get_birthday_date()
        if birthday is None:
            continue

        # Set the year of the birthday to the current year
        birthday = birthday.replace(year=today.year)

        # If the birthday is before today, set it to next year
        if birthday < today:
            birthday = birthday.replace(year=today.year + 1)

        # If this is the first birthday we've found, set it as the next birthday
        if next_birthday is None:
            next_birthday = birthday
            next_birthday_users = [user]
        elif birthday < next_birthday:
            next_birthday = birthday
            next_birthday_users = [user]
        elif birthday == next_birthday:
            next_birthday_users.append(user)

    return next_birthday_users # Returns a list of users with the next birthday (user_id, username, birthday)

