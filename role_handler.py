# This code handles the adding and removing of roles from users. The guild id, user id, and role id is needed.
import discord
from collections import namedtuple


# Return shape for add_role/remove_role. `did_work` is True only when we
# actually invoked the Discord API (or confirmed the role was already in the
# expected state for an idempotent op). Callers use this to decide whether
# the result is worth logging — a "user doesn't have the role" no-op is
# the expected steady state for ~99% of users on any non-birthday day, and
# should not spam the log.
Result = namedtuple("Result", ["did_work", "message"])


class RoleHandler:
    def __init__(self, guild: discord.Guild):
        self.guild = guild

    async def add_role(self, user_id: int, role_id: int) -> Result:
        role = self.guild.get_role(role_id)
        member = await self.guild.fetch_member(user_id)
        if role is None or member is None:
            return Result(False, f"Role or member ({user_id}) not found")
        await member.add_roles(role)
        return Result(True, f"Role {role} has been added to user {member.name}")

    async def get_roles(self, user_id: int, guild_id: int) -> list:
        member = await self.guild.fetch_member(user_id)
        if member is None:
            return []
        return member.roles

    async def remove_role(self, user_id: int, role_id: int) -> Result:
        role = self.guild.get_role(role_id)
        member = await self.guild.fetch_member(user_id)
        if role is None or member is None:
            return Result(False, f"Role or member ({user_id}) not found")
        if role in member.roles:
            await member.remove_roles(role)
            return Result(True, f"Role {role} has been removed from user {member.name}")
        # No-op: user didn't have the role. Silent at the caller — this is
        # the expected steady state for non-birthday users.
        return Result(False, f"User {member.name} does not have the role {role}")
