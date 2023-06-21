# This code handles the adding and removing of roles from users. The guild id, user id, and role id is needed. 
import discord


class RoleHandler:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def add_role(self, user_id: int, role_id: int) -> str:
        role = self.guild.get_role(role_id)
        member = await self.guild.fetch_member(user_id)
        if role is None or member is None:
            return f'Role or member ({user_id}) not found'
        await member.add_roles(role)
        return f'Role {role} has been added to user {member.name}'
    
    async def get_roles(self, user_id: int, guild_id: int) -> list:
        member = await self.guild.fetch_member(user_id)
        if member is None:
            return []
        return member.roles

    async def remove_role(self, user_id: int, role_id: int) -> str:
        role = self.guild.get_role(role_id)
        member = await self.guild.fetch_member(user_id)
        if role is None or member is None:
            return f'Role or member ({user_id}) not found'
        if role in member.roles:
            await member.remove_roles(role)
            return f'Role {role} has been removed from user {member.name}'
        return f'User {member.name} does not have the role {role}'
