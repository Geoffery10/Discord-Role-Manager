import json
import datetime
import random
from role_handler import RoleHandler

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

async def check_birthday(guild):
    role_handler = RoleHandler(guild)
    # Open the JSON file and load the data with encoding utf-8
    with open("users.json") as f:
        data = json.load(f)

    # Check if the user has a birthday in the JSON file
    for user in data:
        await check_user(user, role_handler)
        

async def check_user(user, role_handler):
    global birthday_messages
    # Get the user's birthday
    birthday = datetime.datetime.strptime(
        user["birthday"], "%m/%d").date()

    # Get the current date
    today = datetime.date.today()

    # Check if it's the user's birthday
    if today.month == birthday.month and today.day == birthday.day:
        # Get the user's id
        user_id = user["user_id"]

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
        user_id = user["user_id"]

        # Get the birthday role id
        role_id = 961688424341987409
        try:
            message = await role_handler.remove_role(user_id, role_id)
            print(message.encode('utf-8'))
        except Exception as e:
            print(f"Failed to remove role from user {user_id}")
            print(f"Error: {e}")
    return