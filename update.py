import sqlite3


async def update_database(members, guild):
    # Connect to the database
    conn = sqlite3.connect('discord.db')
    c = conn.cursor()

    # Add all users to the database if their user_id is not already in the sqlite database table users
    for member in members:
        print(f"Checking if user is in db: {member.name}")
        # Check if user_id is in the database
        c.execute("SELECT user_id FROM users WHERE user_id = ?", (member.id,))
        if c.fetchone() is None:
            # If user_id is not in the database, then add it
            c.execute("INSERT INTO users (user_id, username, birthday, tag) VALUES (?, ?, ?, ?)", (member.id, member.name, "00-00", member.discriminator))
            conn.commit()
            print("Added user: " + member.name)
        else:
            # Check if the user's tag is different
            c.execute("SELECT tag FROM users WHERE user_id = ?", (member.id,))
            tag = c.fetchone()[0]
            if tag != member.discriminator:
                # Replace the tag in the database with the new tag
                c.execute("UPDATE users SET tag = ? WHERE user_id = ?", (member.discriminator, member.id))
                conn.commit()
                print("Updated tag for user: " + member.name)

        # Check if user_id is in the user_guilds table
        c.execute("SELECT user_id FROM user_guilds WHERE user_id = ? AND guild_id = ?", (member.id, guild.id))
        if c.fetchone() is None:
            # If user_id is not in the database, then add it
            c.execute("INSERT INTO user_guilds (user_id, guild_id) VALUES (?, ?)", (member.id, guild.id))
            conn.commit()
            print("Added user: " + member.name + " to guild: " + guild.name)

    # Close the database
    conn.close()
