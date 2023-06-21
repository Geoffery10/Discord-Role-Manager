# This code handles interactions with discord.db 

# Imports
import sqlite3
from users import User

# Connect to the database
async def connect():
    conn = sqlite3.connect('discord.db')
    c = conn.cursor()
    return conn, c

# Get all users from the database
async def get_users():
    conn, c = await connect()
    c.execute("SELECT user_id, username, birthday, tag FROM users")
    users = c.fetchall()
    c.close()
    user_objs = []
    for user in users:
        user_objs.append(User(user_id=user[0], username=user[1], birthday=user[2], tag=user[3]))
    return user_objs

# Get a user from the database
async def get_user(user_id):
    conn, c = await connect()
    c.execute("SELECT user_id, username, birthday, tag FROM users WHERE user_id = ?", (user_id,))
    user_data = c.fetchone()
    c.close()
    if user_data:
        user = User(user_data[0], user_data[1], user_data[2], user_data[3])
        return user
    else:
        return None

# Add a user to the database
async def add_user(user_id, username, birthday="00-00", tag="1"):
    conn, c = await connect()
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?)",
              (username, birthday, tag, user_id))
    conn.commit()
    c.close()

# Update a user in the database
async def update_user(user_obj = None, user_id = None, username = None, birthday="00-00", tag="1"):
    if user_obj is None:
        user_obj = User(user_id, username, birthday, tag)
    # Get the user from the database using the user_id
    user = await get_user(user_obj.get_user_id())
    # If the user doesn't exist, add them to the database
    if user is None:
        await add_user(user_obj.get_user_id(), user_obj.get_username(), user_obj.get_birthday(), user_obj.get_tag())
    # If the user does exist, update their information
    else:
        conn, c = await connect()
        c.execute("UPDATE users SET username = ?, birthday = ?, tag = ? WHERE user_id = ?", (user_obj.get_username(), user_obj.get_birthday(), user_obj.get_tag(), user_obj.get_user_id()))
        conn.commit()
        c.close()

# Delete a user from the database
async def delete_user(user_id):
    conn, c = await connect()
    c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    c.close()

# Get all users from a guild (to see if a user is in a guild check the user_id in the user_guilds table for the guild_id) user_guilds:(user_id, guild_id)
async def get_guild_users(guild_id):
    conn, c = await connect()
    c.execute("SELECT user_id, username, birthday, tag FROM users WHERE user_id IN (SELECT user_id FROM user_guilds WHERE guild_id = ?)", (guild_id,))
    users_data = c.fetchall()
    c.close()
    user_objs = []
    for user_data in users_data:
        user_objs.append(User(user_data[0], user_data[1], user_data[2], user_data[3]))
    return user_objs

# Add user to a guild
async def add_user_to_guild(user_id, guild_id):
    if is_user_in_guild(user_id, guild_id):
        print("User is already in guild")
    else:
        conn, c = await connect()
        c.execute("INSERT INTO user_guilds VALUES (?, ?)", (user_id, guild_id))
        conn.commit()
        c.close()

# Remove user from a guild
async def remove_user_from_guild(user_id, guild_id):
    conn, c = await connect()
    c.execute("DELETE FROM user_guilds WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    conn.commit()
    c.close()

# Check if a user is in a guild
async def is_user_in_guild(user_id, guild_id):
    conn, c = await connect()
    c.execute("SELECT user_id, guild_id FROM user_guilds WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    user_data = c.fetchone()
    c.close()
    if user_data:
        return True
    else:
        return False
    
# Update user's tag
async def update_user_tag(user_id, tag):
    conn, c = await connect()
    c.execute("UPDATE users SET tag = ? WHERE user_id = ?", (tag, user_id))
    conn.commit()
    c.close()

# Update user's username
async def update_user_username(user_id, username):
    conn, c = await connect()
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    c.close()

# Update user's birthday
async def update_user_birthday(user_id, birthday):
    conn, c = await connect()
    c.execute("UPDATE users SET birthday = ? WHERE user_id = ?", (birthday, user_id))
    conn.commit()
    c.close()