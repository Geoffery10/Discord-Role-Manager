import asyncio
import discord
from dotenv import load_dotenv
import os
import json

intents = discord.Intents(messages=True, guilds=True)
intents.reactions = True
client = discord.Client(intents=intents)
YOUR_MESSAGE_ID = [1052391751178014781, 1052391831855448105]
reaction_roles = {}
pronouns = {":trap:763101905244389376": 796516467222511626,
            ":confused_anime:557426389180088340": 796516551364050975,
            ":drink_anime:557426135001202708": 796516609862139934}


@client.event
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


@client.event
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


@client.event
async def on_ready():
    # Get the guild object
    guild = client.get_guild(254779349352448001)
    # Return early if the guild is None
    if guild is None:
        return

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

    

    # Add the reactions to the messages
    await add_reactions(pronouns_message, pronouns)
    await add_reactions(other_roles, reaction_roles_trimmed)

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

# Get the TOKEN variable from the environment
TOKEN = os.getenv("TOKEN")
client.run(TOKEN)
