from iDiscord import *


async def update_database(members, guild):
    # Add all users to the database if their user_id is not already in the sqlite database table users
    for member in members:
        # print(f"Checking if user is in db: {member.name}")
        user = await get_user(member.id)
        if user is None:
            # If user_id is not in the database, then add it
            await add_user(member.id, member.name, "00-00", member.discriminator)
            print("Added user: " + member.name)
        else:
            # Check if the user's tag is different
            if user.get_tag() != member.discriminator:
                # Replace the tag in the database with the new tag
                await update_user_tag(member.id, member.discriminator)
                print("Updated tag for user: " + member.name)

            # check if the user's username is different
            if user.get_username() != member.name:
                # Replace the username in the database with the new username
                await update_user_username(member.id, member.name)
                print("Updated username for user: " + member.name)

        # Check if user_id is in the user_guilds table
        if not await is_user_in_guild(member.id, guild.id):
            # If user_id is not in the database, then add it
            await add_user_to_guild(member.id, guild.id)
            print("Added user: " + member.name + " to guild: " + guild.name)
