import datetime
import random
from iDiscord import *
from role_handler import RoleHandler
from users import User
from utils.logger import log
import json

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
    
    # Get all the users_id, username, and birthday from the database
    users = await get_users()
    
    # Keep only users that are in the guild
    users = [user for user in users if guild.get_member(int(user.get_user_id())) is not None]
    
    # Load birthday json for guild
    try:
        with open("birthday.json", 'r') as f:
            data = json.load(f)
    except Exception as e:
        await log(type="error", message=f"Failed to load birthday.json. Error: {e}", severity="severe")
        return
    
    guilds = data['guilds']
    # Find the guild with the specified ID in the list
    guild_info = None
    for i in range(len(guilds)):
        if int(guilds[i]['id']) == guild.id:
            guild_info = {
                "id": int(guilds[i]['id']),
                "name": guilds[i]['name'],
                "birthday_role": int(guilds[i]['birthday_role']),
                "birthday_channel": int(guilds[i]['birthday_channel'])
            }
            break
    
    if guild_info is None:
        await log(type="warning", message=f"Failed to find guild with id {guild.id} in birthday.json", severity="medium")
        return

    # Check if the user has a birthday in the database
    if not users is None:
        for user in users:
            await log(type="debug", message=f"Checking if it's {user.get_username()}'s birthday today...")
            await check_user(user, role_handler, guild, guild_info)

    await log(type="info", message="Checked all users")


async def check_user(user, role_handler, guild, guild_info):
    global birthday_messages
    # Get the user's birthday (format is MM-DD or MM-DD-YYYY in the database) using the birthday key
    if user.get_birthday() == "00-00":
        return
    try:
        birthday = datetime.datetime.strptime(user.get_birthday(), "%m-%d").date()
    except ValueError:
        birthday = datetime.datetime.strptime(user.get_birthday(), "%m-%d-%Y").date()

    # Get the current date
    today = datetime.date.today()

    # Check if it's the user's birthday
    if today.month == birthday.month and today.day == birthday.day:
        # Get the user's id
        user_id = int(user.get_user_id())

        # Get the birthday role id
        role_id = int(guild_info.get("birthday_role"))
        if role_id != -1:
            try:
                message = await role_handler.add_role(user_id, role_id)
                await log(type="info", message=message)
            except Exception as e:
                await log(type="info", message=f"Failed to add role to user {user_id}")
                await log(type="info", message=f"Error: {e}")
        # Send a random birthday message to the general channel
        # Get the general channel by id from the guild
        try:
            birthday_channel = role_handler.guild.get_channel(
                int(guild_info.get("birthday_channel")))
        except Exception as e:
            await log(type="error", message=f"Failed to get birthday channel. Error: {e}", severity="severe")
            return
        # Get a random birthday message
        message = random.choice(birthday_messages)
        # Replace the @USER tag with @mention for the user
        message = message.replace("@USER", f"<@{user_id}>")
        # Send the message to the general channel
        try:
            await birthday_channel.send(message)
        except Exception as e:
            await log(type="error", message=f"Failed to send birthday message. Error: {e}", severity="severe")
            return
    else:
        # Get the user's id
        user_id = int(user.get_user_id())

        # Get the birthday role id
        role_id = int(guild_info.get("birthday_role"))
        if role_id != -1:
            try:
                message = await role_handler.remove_role(user_id, int(role_id))
                await log(type="info", message=message.encode('utf-8'))
            except Exception as e:
                await log(type="error",
                    message=f"Failed to remove role from user {user_id}. Error: {e}", severity="high")


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

