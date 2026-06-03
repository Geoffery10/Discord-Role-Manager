import re
import discord
from discord import app_commands
from dotenv import load_dotenv
import os
import json
from birthday import *
from update import update_database, check_if_update_needed
from iDiscord import *
from utils.logger import log

intents = discord.Intents(messages=True, guilds=True, members=True, reactions=True, presences=True)
intents.reactions = True
YOUR_MESSAGE_ID = [1052391751178014781, 1052391831855448105]
reaction_roles = {}
pronouns = {":trap:763101905244389376": 796516467222511626,
            ":confused_anime:557426389180088340": 796516551364050975,
            ":drink_anime:557426135001202708": 796516609862139934}
guilds = [254779349352448001, 779429002657792020,
          786690956514426910, 580445867132321798,
          855809352420950016, 1413215067398475941]

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def load_roles(path="roles.json"):
    with open(path, "r") as f:
        data = json.load(f)
    # Support old flat format {emoji: role_id} and new guild-scoped {guild_id: {emoji: role_id}}
    if data and not any(isinstance(v, dict) for v in data.values()):
        return {"254779349352448001": data}
    return data

def flatten_roles(roles_dict):
    flat = {}
    for guild_id, mapping in roles_dict.items():
        for emoji, role_id in mapping.items():
            flat[emoji] = int(role_id) if isinstance(role_id, str) else role_id
    return flat


def load_roles(path="roles.json"):
    with open(path, "r") as f:
        data = json.load(f)
    # Support old flat format {emoji: role_id} and new guild-scoped {guild_id: {emoji: role_id}}
    if data and not any(isinstance(v, dict) for v in data.values()):
        return {"254779349352448001": data}
    return data


def flatten_roles(roles_dict):
    flat = {}
    for guild_id, mapping in roles_dict.items():
        for emoji, role_id in mapping.items():
            flat[emoji] = int(role_id) if isinstance(role_id, str) else role_id
    return flat


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def on_ready(self):
        global guilds
        # Sync the guilds table with every guild the bot is currently in
        from iDiscord import sync_guilds_table
        await sync_guilds_table(client)

        # Get the guild object
        guild = client.get_guild(254779349352448001)
        # Return early if the guild is None
        if guild is None:
            return

        await log(type="info", message=f"Syncing trees...")
        for sync_guild in guilds:
            await tree.sync(guild=client.get_guild(sync_guild))
        await log(type="info", message="Synced trees")
        # Get the message object
        channel = guild.get_channel(796511958189735966)
        pronouns_message = await channel.fetch_message(YOUR_MESSAGE_ID[0])
        other_roles = await channel.fetch_message(YOUR_MESSAGE_ID[1])

        # Return early if the message is None
        if pronouns_message is None or other_roles is None:
            return

        reaction_roles_trimmed = flatten_roles(load_roles("roles.json")).copy()
        # remove pronouns reactions from reaction_roles_trimmed
        for reaction in pronouns.keys():
            reaction_roles_trimmed.pop(reaction, None)

        await log(type="info", message=f"Rolm is now online!")

    async def on_guild_join(self, guild):
        from iDiscord import add_guild_to_table
        await add_guild_to_table(guild.id, guild.name)
        await log(type="info", message=f"Joined guild: {guild.name} ({guild.id})")

    async def on_guild_remove(self, guild):
        from iDiscord import remove_guild_from_table
        await remove_guild_from_table(guild.id)
        await log(type="info", message=f"Left guild: {guild.name} ({guild.id})")

    async def on_message(self, message):
        # Run update tasks in the background if it's a new day
        global guilds
        await check_if_update_needed(client, guilds)

    async def on_raw_reaction_add(self, payload):
        # Check if the message was one of the ones we want
        if payload.message_id in YOUR_MESSAGE_ID:
            roles_dict = load_roles("roles.json")
            roles = flatten_roles(roles_dict)
            for reaction, role_id in roles.items():
                if str(payload.emoji.id) in reaction:
                    role = payload.member.guild.get_role(role_id)
                    try:
                        await payload.member.add_roles(role)
                        await log(type="info",
                            message=f"Added role {role.name} ({role_id}) to {payload.member.name}")
                    except Exception as e:
                        await log(type="error",
                            message=f"Failed to add role {role.name} ({role_id}) to {payload.member.name}")
                        await log(type="error", message=f"Error: {e}", severity="medium")
                    
                    
    async def on_raw_reaction_remove(self, payload):
        # Check if the message was one of the ones we want
        if payload.message_id in YOUR_MESSAGE_ID:
            roles_dict = load_roles("roles.json")
            roles = flatten_roles(roles_dict)
            for reaction, role_id in roles.items():
                if str(payload.emoji.id) in reaction:
                    guild = client.get_guild(payload.guild_id)
                    member = guild.get_member(payload.user_id)
                    role = guild.get_role(role_id)
                    try:
                        await member.remove_roles(role)
                        await log(type="info",
                            message=f"Removed role {role.name} ({role_id}) from {member.name}")
                    except:
                        await log(type="error",
                            message=f"Failed to remove role {role.name} ({role_id}) from {member.name}", severity="medium")
                        

async def add_reactions(message, roles):
    for reaction, role_id in roles.items():
        if reaction not in [r.emoji for r in message.reactions]:
            try:
                await message.add_reaction(reaction)
                # await log(type="info", message=f"Added reaction {reaction} to message {message.id}")
            except discord.HTTPException:
                await log(type="error",
                    message=f"Failed to add reaction {reaction} to message {message.id}. HTTPException", severity="medium")
            # Sleep to avoid rate limit
            # asyncio.sleep(1)


async def print_reaction_roles():
    # Print role reactions with names
    # Use ID to get the role object
    guild = client.get_guild(254779349352448001)
    for reaction, role_id in reaction_roles.items():
        role = discord.utils.get(guild.roles, id=role_id)
        await log(f"<{reaction}> - {role.name}")


# Load the contents of the .env file into the environment
# Load the JSON file into a dictionary
reaction_roles = load_roles("roles.json")

client = MyClient(intents=intents)
tree = app_commands.CommandTree(client)

# Add the guild ids in which the slash command will appear. If it should be in all, remove the argument, but note that it will take some time (up to an hour) to register the command if it's for all guilds.


@tree.command(guilds=[discord.Object(id=254779349352448001), discord.Object(id=786690956514426910), discord.Object(id=779429002657792020), discord.Object(id=855809352420950016), discord.Object(id=1413215067398475941)])
@app_commands.describe(member='the member to add a birthday for')
@app_commands.describe(birthday='the birthday to add in the format MM-DD')
async def add_birthday(interaction: discord.Interaction, member: discord.Member, birthday: str):
    # Check if the birthday is in the correct format (MM/DD or MM-DD) with regex
    if not re.match(r"^(0[1-9]|1[0-2])(/|-)(0[1-9]|[12][0-9]|3[01])$", birthday):
        await interaction.send("The birthday must be in the format MM/DD or MM-DD")
        return    

    # Replace the separator with a dash (-) to standardize the format
    birthday = birthday.replace("/", "-")
    
    # Get the user from the database
    user = await get_user(member.id)
    # If the user doesn't exist, add them to the database
    if user is None:
        user = await add_user(member.id, member.name, birthday, member.discriminator)
        await log(type="debug", message="Added user: " + member.name)

    # Check if the birthday is not "00-00"
    if user.get_birthday() != "00-00":
        old_birthday = user.get_birthday()
        await interaction.response.send_message(f"Updated {member.name}'s birthday from {old_birthday} to {birthday}.", ephemeral=True)
        await log(type="info",
            message=f"Updated {member.name}'s birthday from {old_birthday} to {birthday}.")
    else:
        await interaction.response.send_message(f"Added {member.name}'s birthday ({birthday}) to the database.", ephemeral=True)
        await log(type="info",
            message=f"Added {member.name}'s birthday ({birthday}) to the database.")

    # Update the user's birthday in the database
    user.set_birthday(birthday)
    await update_user(user_obj=user)


@tree.command(guilds=[discord.Object(id=254779349352448001), discord.Object(id=786690956514426910), discord.Object(id=779429002657792020), discord.Object(id=855809352420950016), discord.Object(id=1413215067398475941)], description="Get the next birthday")
async def next_birthday(interaction: discord.Interaction):
    users = await find_next_birthday(interaction.guild) # Returns a list of users (user: user_id, username, birthday)
    if len(users) == 0:
        await interaction.response.send_message("There are no birthdays in the database.", ephemeral=True)
        return
    else:
        user_mentions = [f"<@{user.get_user_id()}>" for user in users]
        await interaction.response.send_message(f"The next birthday is on {users[0].get_birthday()} and belongs to: {', '.join(user_mentions)}.", ephemeral=True)

@tree.command(guilds=[discord.Object(id=786690956514426910)], description="Update DB")
async def update_db(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    global guilds
    await log(type="info", message="Updating database")
    for guild_id in guilds:
        guild = client.get_guild(guild_id)
        members = guild.members
        await update_database(members, guild)
        channel = interaction.channel
        await channel.send(f"Updated database for {guild.name}.")
    await interaction.followup.send("Finished updating database.")
    await log(type="info", message="Finished updating database")

    

# Get the TOKEN variable from the environment
load_dotenv()
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)
