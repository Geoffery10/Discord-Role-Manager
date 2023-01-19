import asyncio
import datetime
import re
import discord
from discord import app_commands
from discord.app_commands import Choice
from discord.ext import commands
from dotenv import load_dotenv
import os
import json
from birthday import *

intents = discord.Intents(messages=True, guilds=True)
intents.reactions = True
YOUR_MESSAGE_ID = [1052391751178014781, 1052391831855448105]
reaction_roles = {}
pronouns = {":trap:763101905244389376": 796516467222511626,
            ":confused_anime:557426389180088340": 796516551364050975,
            ":drink_anime:557426135001202708": 796516609862139934}


class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    async def on_ready(self):
        # Get the guild object
        guild = client.get_guild(254779349352448001)
        # Return early if the guild is None
        if guild is None:
            return

        await tree.sync(guild=guild)
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

    async def on_message(self, message):
        # Run update tasks in the background if it's a new day
        await check_if_update_needed()

    async def on_raw_reaction_add(payload):
        print(f"Payload: {payload}")
        # Get the user object
        user = await client.fetch_user(payload.user_id)
        if not user:
            print(f"User {payload.user_id} not found")
            return
        # Get the message object
        message = payload.message_id
        guild = client.get_guild(payload.guild_id)
        # Check if the reaction is on the specific message
        if message in YOUR_MESSAGE_ID:
            print(f"Reaction added by {user.name}")
            for reaction, role_id in reaction_roles.items():
                print(f"Reaction: {reaction}".encode("utf-8"))
                print(f"Emoji: {payload.emoji.id}".encode("utf-8"))
                if str(payload.emoji.id) in reaction:
                    role = discord.utils.get(guild.roles, id=role_id)
                    member = await guild.fetch_member(user.id)
                    if member is None:
                        print(f"Member {user.name} not found")
                        return
                    await member.add_roles(role)
                    return

    async def on_raw_reaction_remove(payload):
        print(f"Payload: {payload}")
        # Get the user object
        user = await client.fetch_user(int(payload.user_id))
        if not user:
            print(f"User {payload.user_id} not found")
            return
        # Get the message object
        message = payload.message_id
        guild = client.get_guild(payload.guild_id)
        # Check if the reaction is on the specific message
        if message in YOUR_MESSAGE_ID:
            print(f"Reaction removed by {user.name}")
            for reaction, role_id in reaction_roles.items():
                print(f"Reaction: {reaction}".encode("utf-8"))
                print(f"Emoji: {payload.emoji.id}".encode("utf-8"))
                if str(payload.emoji.id) in reaction:
                    role = discord.utils.get(guild.roles, id=role_id)
                    member = await guild.fetch_member(user.id)
                    if member is None:
                        print(f"Member {user.name} not found")
                        return
                    await member.remove_roles(role)
                    return


async def update():
    # Run Daily Tasks
    print("Running daily tasks")
    # Update Birthday Roles
    print("Updating Birthday Roles")
    await check_birthday(guild=client.get_guild(254779349352448001))


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
@tree.command(guild=discord.Object(id=254779349352448001))
@app_commands.describe(member='the member to add a birthday for')
@app_commands.describe(birthday='the birthday to add in the format MM/DD')
async def add_birthday(interaction: discord.Interaction, member: discord.Member, birthday: str):
    # Check if the user has the appropriate role to add birthdays
    '''
    if not interaction.author.guild_permissions.manage_roles:
        await interaction.send("You do not have the appropriate role to add birthdays.")
        return
    '''
    # Check if the birthday is in the correct format (MM/DD) with regex
    if not re.match(r"^(0[1-9]|1[0-2])/(0[1-9]|[12][0-9]|3[01])$", birthday):
        await interaction.send("The birthday must be in the format MM/DD")
        return
    
    # Open the JSON file and load the data
    with open("users.json") as f:
        data = json.load(f)

    # Check if the user already has a birthday in the JSON file
    for d in data:
        if d["user_id"] == f'{member.id}':
            await interaction.response.send_message("This user already has a birthday saved.")
            return

    # Add the user's birthday to the JSON file
    data.append(
        {"user_id": f"{member.id}", "username": f"{member.name}", "birthday": f"{birthday}"})
    print(data)
    with open("users.json", "w") as f:
        json.dump(data, f)
    await interaction.response.send_message(f"Added {member.name}'s birthday to the database.")

@tree.command(guild=discord.Object(id=254779349352448001), description="Get the next birthday")
async def next_birthday(interaction: discord.Interaction):
    # Open the JSON file and load the data
    with open("users.json") as f:
        data = json.load(f)

    # Get the current date
    today = datetime.date.today()

    # Initialize the next_birthday variable with a date in the future
    # Use today's date as the default -1 day
    next_birthday = datetime.date(3000, 1, 1)

    # Initialize an empty list to store the users with the next birthday
    next_birthday_users = []

    # Iterate through each user in the data
    for user in data:
        # Get the user's birthday
        birthday = datetime.datetime.strptime(user["birthday"], "%m/%d").date()
        # Set the year to the current year
        birthday = birthday.replace(year=today.year)
        print(f"{user['username']} - {birthday} - {today} - {next_birthday}")

        # Check if the user's birthday is in the future and is not today
        if birthday > today and birthday < next_birthday:
            # Update the next_birthday variable
            next_birthday = birthday
            next_birthday_users = []
            # Add the user to the list of users with the next birthday
            next_birthday_users.append(user["user_id"])
        # Check if there is multiple people with the same birthday
        elif birthday == next_birthday:
            next_birthday_users.append(user["user_id"])
    #get the user objects
    user_objects = []
    for user in next_birthday_users:
        user_objects.append(await client.fetch_user(user))
    user_names = [user.name for user in user_objects]
    # format the message
    message = f"The next birthday is on {next_birthday.strftime('%m/%d')} and belongs to: {', '.join(user_names)}."
    await interaction.response.send_message(message)

    

# Get the TOKEN variable from the environment
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)
