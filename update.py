from iDiscord import *
from users import User
import asyncio
import datetime
from utils.logger import log
import json
from birthday import check_birthday


async def update(client, guilds):
    # Run Daily Tasks
    await log(type="info", message="Running update tasks")
    # Update Birthday Roles
    await log(type="info", message="Updating Birthday Roles")
    for guild_id in guilds:
        guild = client.get_guild(guild_id)
        # The bot may have been removed from a guild since main.py's
        # hardcoded list was last updated. client.get_guild() returns None
        # in that case, and accessing .name on None would crash the whole
        # daily task loop — silently skipping every guild that comes after.
        # Skip with a warning so the rest of the guilds still get processed.
        if guild is None:
            await log(
                type="warning",
                message=f"Guild id {guild_id} is in the configured list but the bot is not a member; skipping",
                severity="medium",
            )
            continue
        await log(type="info", message=f"Updating birthday roles for {guild.name}")
        await check_birthday(guild)
    # Update the database for each guild
    await log(type="info", message="Updating database")
    # Get members from the guilds

    tasks = []
    for guild_id in guilds:
        guild = client.get_guild(guild_id)
        if guild is None:
            continue
        members = guild.members
        await log(type="info", message=f"Updating database for {guild.name}")
        task = asyncio.create_task(update_database(members, guild))
        tasks.append(task)
    await asyncio.gather(*tasks)
    await log(type="info", message="Finished update tasks")


async def check_if_update_needed(client, guilds):
    # Load last_update from a JSON file to check if it's a new day
    with open("last_update.json") as f:
        last_update = json.load(f)
    # Get the current date
    today = datetime.date.today()
    # Parse current date to a string 00/00/0000
    today = today.strftime("%m/%d/%Y")
    # Check if it's a new day
    if today != last_update["last_update"]:
        # Update last_update in the JSON file
        with open("last_update.json", "w") as f:
            json.dump({"last_update": today}, f)
        # Run the update tasks in the background
        await update(client, guilds)


async def update_database(members, guild):
    # Add all users to the database if their user_id is not already in the sqlite database table users
    for member in members:
        # await log(type="info", message=f"Checking if user is in db: {member.name}")
        user = await get_user(member.id)
        if user is None:
            # If user_id is not in the database, then add it
            await add_user(member.id, member.name, "00-00", member.discriminator, member.avatar.key if member.avatar else None)
            await log(type="info", message="Added user: " + member.name)
        else:
            # Check if the user's tag is different
            if user.get_tag() != member.discriminator:
                # Replace the tag in the database with the new tag
                await update_user_tag(member.id, member.discriminator)
                await log(type="info", message="Updated tag for user: " + member.name)

            # check if the user's username is different
            if user.get_username() != member.name:
                # Replace the username in the database with the new username
                await update_user_username(member.id, member.name)
                await log(type="info", message="Updated username for user: " + member.name)

            # check if the user's avatar is different
            avatar_key = member.avatar.key if member.avatar else None
            if user.get_avatar() != avatar_key:
                await update_user_avatar(member.id, avatar_key)
                await log(type="info", message="Updated avatar for user: " + member.name)

        # Check if user_id is in the user_guilds table
        if not await is_user_in_guild(member.id, guild.id):
            # If user_id is not in the database, then add it
            await add_user_to_guild(member.id, guild.id)
            await log(type="info", message="Added user: " +
                member.name + " to guild: " + guild.name)
