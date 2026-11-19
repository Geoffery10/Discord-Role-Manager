import datetime
import random
from collections import namedtuple

import discord

from iDiscord import *
from role_handler import RoleHandler
from users import User, parse_month_day
from utils.logger import log
import json

# Return shape for the membership probe.
#   member      - the discord.Member when the user is currently in the guild
#   known_gone  - True only when Discord answered with a definitive 404, the
#                 single case where pruning the user_guilds row is safe
Membership = namedtuple("Membership", ["member", "known_gone"])


async def resolve_membership(guild, user_id):
    """Authoritatively determine whether user_id is still in guild.

    guild.get_member() is cache-only: it returns None for anyone not in the
    gateway cache, which is NOT the same as "left the server". Only a 404 from
    fetch_member proves the user is gone. Any other failure means "unknown", so
    the caller must skip posting but must not delete the row.
    """
    member = guild.get_member(user_id)
    if member is not None:
        return Membership(member, False)
    try:
        return Membership(await guild.fetch_member(user_id), False)
    except discord.NotFound:
        return Membership(None, True)
    except Exception as e:
        await log(type="warning",
                  message=f"Could not verify membership for user {user_id} in {guild.name}. Error: {e}",
                  severity="medium")
        return Membership(None, False)

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
    
    # Get the users that are in this guild in a single SQL query.
    # This replaces the previous per-user is_user_in_guild() loop, which
    # issued one query per user and was visibly slow on the bot server
    # (one guild took ~19s for ~200 users).
    users = await get_guild_users(guild.id)
    
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
    if users is not None:
        await log(type="debug", message=f"Checking birthdays for {len(users)} users in {guild.name}")
        for user in users:
            await check_user(user, role_handler, guild, guild_info)

    await log(type="info", message="Checked all users")


async def check_user(user, role_handler, guild, guild_info):
    global birthday_messages
    user_id = int(user.get_user_id())

    # user_guilds is only ever added to, never pruned, so a row can outlive the
    # member's actual presence in the server. Posting a birthday mention for a
    # departed user renders as "@unknown-user" in the channel, and the role
    # calls below would fail on a ghost. Verify membership first: prune the
    # stale row and skip, so nothing is posted for someone who isn't there.
    membership = await resolve_membership(guild, user_id)
    if membership.known_gone:
        await remove_user_from_guild(user_id, guild.id)
        await log(type="warning",
                  message=f"{user.get_username()} ({user_id}) is no longer in {guild.name}. "
                          f"Removed from user_guilds and skipped",
                  severity="medium")
        return
    if membership.member is None:
        # Membership could not be confirmed (transient failure). Don't prune a
        # row we can't disprove, and don't risk posting a broken mention.
        await log(type="warning",
                  message=f"Skipped birthday check for {user.get_username()} ({user_id}) in "
                          f"{guild.name}: membership could not be verified",
                  severity="medium")
        return

    # Get the user's birthday (format is MM-DD or MM-DD-YYYY in the database) using the birthday key
    if user.get_birthday() == "00-00":
        return
    try:
        birthday = parse_month_day(user.get_birthday())
    except ValueError as e:
        await log(type="warning",
                  message=f"Skipping {user.get_username()} ({user_id}) in {guild.name}: "
                          f"unparseable birthday {user.get_birthday()!r}. Error: {e}",
                  severity="medium")
        return

    # Get the current date
    today = datetime.date.today()

    # Check if it's the user's birthday
    if today.month == birthday.month and today.day == birthday.day:
        # Get the birthday role id
        role_id = int(guild_info.get("birthday_role"))
        if role_id != -1:
            try:
                result = await role_handler.add_role(user_id, role_id)
                if result.did_work:
                    await log(type="info", message=result.message)
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
        # Get the birthday role id
        role_id = int(guild_info.get("birthday_role"))
        if role_id != -1:
            try:
                result = await role_handler.remove_role(user_id, int(role_id))
                # Only log when the API was actually called (i.e. the user
                # had the role). The "user does not have the role" no-op is
                # the expected steady state and was previously spamming the
                # log with one INFO line per user per day.
                if result.did_work:
                    await log(type="info", message=result.message)
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

