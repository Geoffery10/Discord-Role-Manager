# This code handles interactions with discord.db 

# Imports
import sqlite3
from users import User
from utils.logger import log

# ------------------------------------------------------------------
# Schema migration
# ------------------------------------------------------------------
def _ensure_schema():
    conn = sqlite3.connect('discord.db')
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    c = conn.cursor()
    # If the users table doesn't exist yet (fresh checkout), nothing to migrate
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not c.fetchone():
        conn.close()
        return
    c.execute("PRAGMA table_info(users)")
    cols = {row[1] for row in c.fetchall()}
    if "avatar" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT NULL")
        conn.commit()
    conn.close()

_ensure_schema()

# Connect to the database
async def connect():
    conn = sqlite3.connect('discord.db')
    conn.execute("PRAGMA busy_timeout = 5000")
    c = conn.cursor()
    return conn, c

# Get all users from the database
async def get_users():
    conn, c = await connect()
    c.execute("SELECT user_id, username, birthday, tag, avatar FROM users")
    users = c.fetchall()
    conn.close()
    user_objs = []
    for user in users:
        user_objs.append(User(user_id=user[0], username=user[1], birthday=user[2], tag=user[3], avatar=user[4]))
    return user_objs

# Get a user from the database
async def get_user(user_id):
    conn, c = await connect()
    c.execute("SELECT user_id, username, birthday, tag, avatar FROM users WHERE user_id = ?", (user_id,))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        user = User(user_data[0], user_data[1], user_data[2], user_data[3], user_data[4])
        return user
    else:
        return None

# Add a user to the database
async def add_user(user_id, username, birthday="00-00", tag="1", avatar=None):
    conn, c = await connect()
    c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?)",
              (username, birthday, tag, user_id, avatar))
    conn.commit()
    conn.close()
    return User(user_id, username, birthday, tag, avatar)

# Update a user in the database
async def update_user(user_obj = None, user_id = None, username = None, birthday="00-00", tag="1", avatar=None):
    if user_obj is None:
        user_obj = User(user_id, username, birthday, tag, avatar)
    # Get the user from the database using the user_id
    user = await get_user(user_obj.get_user_id())
    # If the user doesn't exist, add them to the database
    if user is None:
        await add_user(user_obj.get_user_id(), user_obj.get_username(), user_obj.get_birthday(), user_obj.get_tag(), user_obj.get_avatar())
    # If the user does exist, update their information
    else:
        conn, c = await connect()
        c.execute("UPDATE users SET username = ?, birthday = ?, tag = ?, avatar = ? WHERE user_id = ?", (user_obj.get_username(), user_obj.get_birthday(), user_obj.get_tag(), user_obj.get_avatar(), user_obj.get_user_id()))
        conn.commit()
        conn.close()

# Update user's avatar
async def update_user_avatar(user_id, avatar):
    conn, c = await connect()
    c.execute("UPDATE users SET avatar = ? WHERE user_id = ?", (avatar, user_id))
    conn.commit()
    conn.close()

# Delete a user from the database
async def delete_user(user_id):
    conn, c = await connect()
    c.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# Get all users from a guild (to see if a user is in a guild check the user_id in the user_guilds table for the guild_id) user_guilds:(user_id, guild_id)
async def get_guild_users(guild_id):
    conn, c = await connect()
    c.execute("SELECT user_id, username, birthday, tag, avatar FROM users WHERE user_id IN (SELECT user_id FROM user_guilds WHERE guild_id = ?)", (guild_id,))
    users_data = c.fetchall()
    conn.close()
    user_objs = []
    for user_data in users_data:
        user_objs.append(User(user_data[0], user_data[1], user_data[2], user_data[3], user_data[4]))
    return user_objs

# Add user to a guild
async def add_user_to_guild(user_id, guild_id):
    if await is_user_in_guild(user_id, guild_id):
        # await log(type="debug", message="User is already in guild")
        pass
    else:
        conn, c = await connect()
        c.execute("INSERT INTO user_guilds VALUES (?, ?)", (user_id, guild_id))
        conn.commit()
        conn.close()
        await log(type="debug", message=f"Added user: {user_id} to guild {guild_id}")

# Remove user from a guild
async def remove_user_from_guild(user_id, guild_id):
    conn, c = await connect()
    c.execute("DELETE FROM user_guilds WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    conn.commit()
    conn.close()

# Check if a user is in a guild
async def is_user_in_guild(user_id, guild_id):
    conn, c = await connect()
    c.execute("SELECT user_id, guild_id FROM user_guilds WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    user_data = c.fetchone()
    conn.close()
    if user_data:
        return True
    else:
        return False
    
# Update user's tag
async def update_user_tag(user_id, tag):
    conn, c = await connect()
    c.execute("UPDATE users SET tag = ? WHERE user_id = ?", (tag, user_id))
    conn.commit()
    conn.close()

# Update user's username
async def update_user_username(user_id, username):
    conn, c = await connect()
    c.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
    conn.commit()
    conn.close()

# Update user's birthday
async def update_user_birthday(user_id, birthday):
    conn, c = await connect()
    c.execute("UPDATE users SET birthday = ? WHERE user_id = ?", (birthday, user_id))
    conn.commit()
    conn.close()