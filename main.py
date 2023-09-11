import asyncio
import datetime
import re
import discord
from discord import app_commands
from dotenv import load_dotenv
import os
import json
from birthday import *
from update import update_database
import threading
from users import User
from iDiscord import *

intents = discord.Intents(messages=True, guilds=True, members=True, reactions=True, presences=True)
intents.reactions = True
YOUR_MESSAGE_ID = [1052391751178014781, 1052391831855448105]
reaction_roles = {}
pronouns = {":trap:763101905244389376": 796516467222511626,
            ":confused_anime:557426389180088340": 796516551364050975,
            ":drink_anime:557426135001202708": 796516609862139934}
guilds = [254779349352448001, 779429002657792020,
          786690956514426910, 580445867132321798, 855809352420950016]


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def on_ready(self):
        global guilds
        # Get the guild object
        guild = client.get_guild(254779349352448001)
        # Return early if the guild is None
        if guild is None:
            return

        for sync_guild in guilds:
            await tree.sync(guild=client.get_guild(sync_guild))
        print("Synced trees")
        # Get the message object
        channel = guild.get_channel(796511958189735966)
        pronouns_message = await channel.fetch_message(YOUR_MESSAGE_ID[0])
        other_roles = await channel.fetch_message(YOUR_MESSAGE_ID[1])

        # Return early if the message is None
        if pronouns_message is None or other_roles is None:
            return

        reaction_roles_trimmed = reaction_roles.copy()
        # remove pronouns reactions from reaction_roles_trimmed
        for reaction in pronouns.keys():
            reaction_roles_trimmed.pop(reaction)

        print(f"\tRolm is now online!")

    async def on_message(self, message):
        # Run update tasks in the background if it's a new day
        await check_if_update_needed()

    async def on_raw_reaction_add(self, payload):
        # Check if the message was one of the ones we want
        if payload.message_id in YOUR_MESSAGE_ID:
            # Load roles from json file
            with open("roles.json", "r") as f:
                roles = json.load(f)
            # Get reaction used and see if it's in the roles
            for reaction, role_id in roles.items():
                if str(payload.emoji.id) in reaction:
                    # Add the role to the user
                    role = payload.member.guild.get_role(role_id)
                    try:
                        await payload.member.add_roles(role)
                        print(f"Added role {role.name} ({role_id}) to {payload.member.name}")
                    except:
                        print(f"Failed to add role {role.name} ({role_id}) to {payload.member.name}")
                    
                    
    async def on_raw_reaction_remove(self, payload):
        # Check if the message was one of the ones we want
        if payload.message_id in YOUR_MESSAGE_ID:
            # Load roles from json file
            with open("roles.json", "r") as f:
                roles = json.load(f)
            # Get reaction used and see if it's in the roles
            for reaction, role_id in roles.items():
                if str(payload.emoji.id) in reaction:
                    # Remove the role from the user
                    guild = client.get_guild(payload.guild_id)
                    member = guild.get_member(payload.user_id)
                    role = guild.get_role(role_id)
                    try:
                        await member.remove_roles(role)
                        print(f"Removed role {role.name} ({role_id}) from {member.name}")
                    except:
                        print(f"Failed to remove role {role.name} ({role_id}) from {member.name}")


async def update():
    # Run Daily Tasks
    print("Running update tasks")
    # Update Birthday Roles
    print("Updating Birthday Roles")
    await check_birthday(guild=client.get_guild(254779349352448001))
    # Update the database for each guild
    print("Updating database")
    # Get members from the guilds
    global guilds
    tasks = []
    for guild_id in guilds:
        guild = client.get_guild(guild_id)
        members = guild.members
        print(f"Updating database for {guild.name}")
        task = asyncio.create_task(update_database(members, guild))
        tasks.append(task)
    await asyncio.gather(*tasks)
    print("Finished update tasks")


async def check_if_update_needed():  
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
        await update()

async def add_reactions(message, roles):
    for reaction, role_id in roles.items():
        if reaction not in [r.emoji for r in message.reactions]:
            try:
                await message.add_reaction(reaction)
                # print(f"Added reaction {reaction} to message {message.id}")
            except discord.HTTPException:
                print(
                    f"Failed to add reaction {reaction} to message {message.id}")
            # Sleep to avoid rate limit
            # asyncio.sleep(1)

def print_reaction_roles():
    # Print role reactions with names
    # Use ID to get the role object
    guild = client.get_guild(254779349352448001)
    for reaction, role_id in reaction_roles.items():
        role = discord.utils.get(guild.roles, id=role_id)
        print(f"<{reaction}> - {role.name}")


# Load the contents of the .env file into the environment
# Load the JSON file into a dictionary
with open("roles.json") as f:
    reaction_roles = json.load(f)

load_dotenv()

client = MyClient(intents=intents)
tree = app_commands.CommandTree(client)

# Add the guild ids in which the slash command will appear. If it should be in all, remove the argument, but note that it will take some time (up to an hour) to register the command if it's for all guilds.


@tree.command(guilds=[discord.Object(id=254779349352448001), discord.Object(id=786690956514426910), discord.Object(id=779429002657792020), discord.Object(id=855809352420950016)])
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
        print("Added user: " + member.name)      

    # Check if the birthday is not "00-00"
    if user.get_birthday() != "00-00":
        old_birthday = user.get_birthday()
        await interaction.response.send_message(f"Updated {member.name}'s birthday from {old_birthday} to {birthday}.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Added {member.name}'s birthday ({birthday}) to the database.", ephemeral=True)
    
    # Update the user's birthday in the database
    user.set_birthday(birthday)
    await update_user(user_obj=user)


@tree.command(guilds=[discord.Object(id=254779349352448001), discord.Object(id=786690956514426910), discord.Object(id=779429002657792020), discord.Object(id=855809352420950016)], description="Get the next birthday")
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
    print("Updating database")
    for guild_id in guilds:
        guild = client.get_guild(guild_id)
        members = guild.members
        await update_database(members, guild)
        channel = interaction.channel
        await channel.send(f"Updated database for {guild.name}.")
    await interaction.followup.send("Finished updating database.")
    print("Finished updating database")

    

# Get the TOKEN variable from the environment
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)
