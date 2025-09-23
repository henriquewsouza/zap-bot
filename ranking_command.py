# ranking_command.py
import discord
from discord.ext import commands
from ranking_handler import RankingHandler
import boto3
import json

class RankingCommand:
    """
    Handles the ranking command with minimum 3 matches requirement.
    """
    
    def __init__(self, s3, bucket_name, members_key):
        self.ranking_handler = RankingHandler(s3, bucket_name, members_key)
    
    async def handle_ranking(self, ctx, *, args: str = None):
        """
        !ranking [YYYY‑MM | -all] [--exclude-mix | --no-mix | -nm]
        Shows rankings with minimum 3 matches played requirement.
        """
        # Parse arguments
        month_arg = None
        exclude_mixes = False
        if args:
            for a in args.split():
                la = a.lower()
                if la in ("--exclude-mix", "--no-mix", "-nm"):
                    exclude_mixes = True
                elif la != "":
                    month_arg = a

        # Load members data
        try:
            response = self.ranking_handler.s3.get_object(
                Bucket=self.ranking_handler.bucket, 
                Key=self.ranking_handler.members_key
            )
            members = json.loads(response["Body"].read().decode("utf-8"))
        except Exception:
            await ctx.send("Erro ao carregar members.json do S3.")
            return

        discord_to_gc = {did: str(info["gc"]) for did, info in members.items() if info.get("gc")}
        gc_to_nick = {str(info["gc"]): info.get("nickname", f"Unknown({info['gc']})")
                      for info in members.values() if info.get("gc")}
        group_gc_ids = set(gc_to_nick.keys())
        if not group_gc_ids:
            await ctx.send("Nenhum GC id configurado no members.json.")
            return

        # Determine period
        all_flag = (month_arg == "-all")
        if month_arg and not all_flag:
            try:
                from datetime import datetime
                datetime.strptime(month_arg, "%Y-%m")
                month_year = month_arg
            except ValueError:
                await ctx.send("Use YYYY‑MM ou -all. Ex.: `!ranking 2025-07 --no-mix`")
                return
        else:
            from datetime import datetime
            month_year = datetime.now().strftime("%Y-%m")

        # Get player data
        players = []
        prefix = ""
        for did, nick in ((did, gc_to_nick[str(info["gc"])])
                          for did, info in members.items() if info.get("gc")):
            gc = str(members[did]["gc"])
            stats_key = f"players/{gc}/stats-{month_year}.json"
            if all_flag:
                stats_files = self.ranking_handler._list_prefix(f"players/{gc}/stats-")
            else:
                stats_files = [stats_key]

            # Aggregate stats
            agg = self.ranking_handler._aggregate_from_stats_files(stats_files)
            if not agg or agg.get("matches", 0) < 3:  # Minimum 3 matches requirement
                continue
            players.append({"nickname": nick, **agg})

        if not players:
            await ctx.send("Nenhum jogador com pelo menos 3 partidas encontrado para este período.")
            return

        # Create rankings
        def sort_metric(lst, key): 
            return sorted(lst, key=lambda x: x[key], reverse=True)

        def txt(lst, key, label):
            return "\n".join(f"{i+1}. {p['nickname']} – {label}: {p[key]:.2f} ({p['matches']} part.)"
                             for i, p in enumerate(lst))

        embed = discord.Embed(
            title=f"Ranking {('All Time' if all_flag else month_year)}"
                  f"{' (sem mixes)' if exclude_mixes else ''} (min. 3 partidas)",
            description="Leaderboards do grupo",
            color=0x3498db
        )
        embed.add_field(name="KDR", value=f"```{txt(sort_metric(players,'kdr'),'kdr','KDR')}```", inline=False)
        embed.add_field(name="ADR", value=f"```{txt(sort_metric(players,'adr'),'adr','ADR')}```", inline=False)
        embed.add_field(name="Avg FK", value=f"```{txt(sort_metric(players,'avg_fk'),'avg_fk','Avg FK')}```", inline=False)
        embed.add_field(name="Win Rate", value=f"```{txt(sort_metric(players,'win_rate'),'win_rate','Win Rate')}```",
                        inline=False)
        await ctx.send(embed=embed)

