from __future__ import annotations

import random
from typing import List, Optional

import discord
from discord.ext import commands

from ..levels import LevelService
from ..team_balance import build_team_message, generate_partitions


class MixCog(commands.Cog):
    def __init__(self, bot: commands.Bot, levels: LevelService, bot_admins: List[int]):
        self.bot = bot
        self.levels = levels
        self.bot_admins = set(bot_admins)
        self.mix_in_progress = False

    async def _parse_mix_args(self, ctx: commands.Context):
        args = ctx.message.content.split()[1:]  # skip the command name
        combination_count = 1
        if args and args[0].isdigit():
            combination_count = int(args[0])
            args = args[1:]

        mode: Optional[str] = None
        exclusions: List[discord.Member] = []
        extras: List[discord.Member] = []
        duelo: List[discord.Member] = []
        converter = commands.MemberConverter()

        for arg in args:
            if arg.lower() in ("-e", "--exclude"):
                mode = "exclude"
            elif arg.lower() in ("-x", "--extra"):
                mode = "extra"
            elif arg.lower() in ("-t", "--duelo"):
                mode = "duelo"
            else:
                try:
                    member = await converter.convert(ctx, arg)
                except commands.BadArgument:
                    continue
                if mode is None:
                    mode = "extra"
                if mode == "exclude":
                    exclusions.append(member)
                elif mode == "extra":
                    extras.append(member)
                elif mode == "duelo":
                    duelo.append(member)
        return combination_count, exclusions, extras, duelo

    def _get_mix_members(self, ctx: commands.Context, exclusions: List[discord.Member], extras: List[discord.Member]):
        members: List[discord.Member] = []
        if ctx.author.voice is not None:
            voice_members = [m for m in ctx.author.voice.channel.members if not m.bot]
            members.extend(voice_members)
        exclusions_ids = {m.id for m in exclusions}
        members = [m for m in members if m.id not in exclusions_ids]
        for m in extras:
            if all(m.id != x.id for x in members):
                members.append(m)
        return members

    @commands.command(name="mix")
    async def mix(self, ctx: commands.Context):
        """
        !mix [<n>] [--exclude/-e @User …] [--extra/-x @User …] [--duelo/-t @A @B]
        """
        if self.mix_in_progress:
            await ctx.send("A team mix is already in progress. Please wait until it is finished.")
            return

        self.mix_in_progress = True
        try:
            combination_count, exclusions, extras, duelo = await self._parse_mix_args(ctx)
            members = self._get_mix_members(ctx, exclusions, extras)
            if len(members) < 2:
                await ctx.send("There are not enough members to form teams.")
                return

            missing = [m for m in members if self.levels.get_level(m.id) <= 0]
            if missing:
                missing_names = ", ".join(m.display_name for m in missing)
                await ctx.send("The following members do not have a level set: " + missing_names)
                return

            partitions = generate_partitions(members, get_level=lambda m: self.levels.get_level(m.id))

            # Apply duelo constraint (must be opposite teams)
            if duelo:
                if len(duelo) != 2:
                    await ctx.send("Please provide exactly 2 members for the --duelo flag.")
                    return
                if ctx.author.id not in self.bot_admins and any(m.id == ctx.author.id for m in duelo):
                    await ctx.send("You cannot use --duelo flag with yourself as one of the parameters.")
                    return

                def in_team(team, member):
                    return any(m.id == member.id for m in team)

                partitions = [
                    p for p in partitions
                    if not (
                        (in_team(p.team1, duelo[0]) and in_team(p.team1, duelo[1]))
                        or (in_team(p.team2, duelo[0]) and in_team(p.team2, duelo[1]))
                    )
                ]

            if not partitions:
                await ctx.send("No valid team partitions available with the current constraints.")
                return

            combination_count = min(combination_count, len(partitions))
            for i in range(combination_count):
                p = partitions[i]
                msg = build_team_message(
                    p.team1,
                    p.team2,
                    get_level=lambda m: self.levels.get_level(m.id),
                    get_mention=lambda m: m.mention,
                )
                await ctx.send(f"**Combination #{i+1}:**\n" + msg)
        finally:
            self.mix_in_progress = False

    @commands.command(name="arere")
    async def arere(self, ctx: commands.Context):
        """
        !arere
        Random split of current voice channel.
        """
        if ctx.author.voice is None:
            await ctx.send("You need to be in a voice channel to use this command.")
            return
        members = [m for m in ctx.author.voice.channel.members if not m.bot]
        if len(members) < 2:
            await ctx.send("Not enough members in the voice channel to mix teams.")
            return

        random.shuffle(members)
        mid = len(members) // 2
        team1 = members[:mid]
        team2 = members[mid:]
        team1_text = "\n".join(m.mention for m in team1)
        team2_text = "\n".join(m.mention for m in team2)
        await ctx.send(
            "**Random Team Assignment:**\n\n"
            f"**Team 1:**\n{team1_text}\n\n"
            f"**Team 2:**\n{team2_text}"
        )


