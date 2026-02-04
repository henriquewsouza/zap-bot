from __future__ import annotations

import asyncio
from typing import List

import discord
from discord.ext import commands

from ..levels import LevelService


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot, levels: LevelService, bot_admins: List[int]):
        self.bot = bot
        self.levels = levels
        self.bot_admins = set(bot_admins)

    def _is_admin(self, user_id: int) -> bool:
        return user_id in self.bot_admins

    @commands.command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx: commands.Context):
        if not self._is_admin(ctx.author.id):
            await ctx.send("Bot admins only.")
            return
        deleted = await ctx.channel.purge(limit=None)
        confirmation = await ctx.send(f"Cleared {len(deleted)} messages from this channel.")
        await asyncio.sleep(5)
        await confirmation.delete()

    @commands.command(name="setlevel")
    async def setlevel(self, ctx: commands.Context, member: discord.Member, level: int):
        if not self._is_admin(ctx.author.id):
            await ctx.send("Bot admins only.")
            return
        self.levels.set_level(member.id, int(level), nickname=member.display_name)
        await ctx.send(f"Updated {member.mention}'s level to {level}.")

    @commands.command(name="addtemp")
    async def addtemp(self, ctx: commands.Context, member: discord.Member, level: int):
        if not self._is_admin(ctx.author.id):
            await ctx.send("Bot admins only.")
            return
        self.levels.add_temp(member.id, int(level), nickname=member.display_name)
        await ctx.send(f"Temporarily added {member.mention} with level {level}.")

    @commands.command(name="players")
    async def players(self, ctx: commands.Context):
        data = self.levels.store.all()
        if not data and not self.levels.temp_levels:
            await ctx.send("No players are currently in the list.")
            return
        # combine store + temp view
        combined = {}
        for did_str, info in data.items():
            try:
                combined[int(did_str)] = dict(info)
            except Exception:
                continue
        for did, info in self.levels.temp_levels.items():
            combined[did] = {**combined.get(did, {}), **info}

        sorted_players = sorted(combined.items(), key=lambda kv: int(kv[1].get("level", 0) or 0), reverse=True)
        msg_lines = ["**Current Players:**"]
        for user_id, info in sorted_players:
            msg_lines.append(f"**{info.get('nickname', 'Unknown')}** - Level: {info.get('level', 'N/A')}")
        text = "\n".join(msg_lines)
        for i in range(0, len(text), 1900):
            await ctx.send(text[i : i + 1900])

    @commands.command(name="botadmins")
    async def botadmins(self, ctx: commands.Context):
        msg_lines = ["**Bot Admins:**"]
        for admin_id in sorted(self.bot_admins):
            info = self.levels.store.get(admin_id) or {}
            if info:
                msg_lines.append(
                    f"<@{admin_id}> - Nickname: **{info.get('nickname', 'Unknown')}**, Level: **{info.get('level', 'N/A')}**"
                )
            else:
                msg_lines.append(f"<@{admin_id}> - No info available.")
        await ctx.send("\n".join(msg_lines))


