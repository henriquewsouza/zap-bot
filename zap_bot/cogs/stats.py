from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import discord
from discord.ext import commands

from vintao_stats_handler import VintaoLocalStatsHandler


def _load_members(members_path: str = "members.json") -> Dict[str, Any]:
    with open(members_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_stats_file(gc_id: str, month_year: str) -> Dict[str, Any] | None:
    p = Path("players") / str(gc_id) / f"stats-{month_year}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _all_stats_files(gc_id: str) -> List[Path]:
    p = Path("players") / str(gc_id)
    if not p.exists():
        return []
    return sorted(p.glob("stats-*.json"))


def generate_local_summary(stats_data: Dict[str, Any], player_name: str, leaderboard: List[Tuple[str, float]], context: str) -> str:
    """
    Local deterministic replacement for the old AI-generated roast.
    """
    kdr = float(stats_data.get("KDR", 0) or 0)
    adr = float(stats_data.get("ADR", 0) or 0)
    wr = float(stats_data.get("overall_win_rate", 0) or 0)
    fk = float(stats_data.get("average_first_kills_per_match", 0) or 0)
    hs = float(stats_data.get("HS_percent", 0) or 0)

    # leaderboard: [(nick, kdr), ...]
    kdrs = [v for _, v in leaderboard if isinstance(v, (int, float))]
    avg_kdr = sum(kdrs) / len(kdrs) if kdrs else 0.0

    vibe = "monstro" if kdr >= max(1.2, avg_kdr + 0.15) else "ok" if kdr >= max(1.0, avg_kdr - 0.05) else "sofrido"

    if vibe == "monstro":
        return (
            f"🔥 **Resumo:** {player_name} tá voando. KDR {kdr:.2f}, ADR {adr:.0f}, WR {wr:.0f}%.\n"
            f"FK {fk:.2f} e HS {hs:.0f}% — dá pra chamar de carregador.\n"
            + (f"Contexto: {context}" if context else "")
        ).strip()
    if vibe == "ok":
        return (
            f"✅ **Resumo:** {player_name} tá consistente. KDR {kdr:.2f} (média do grupo ~{avg_kdr:.2f}).\n"
            f"ADR {adr:.0f}, WR {wr:.0f}%, FK {fk:.2f}, HS {hs:.0f}%.\n"
            + (f"Contexto: {context}" if context else "")
        ).strip()
    # sofrido
    # pick someone mid-table if possible
    comp = None
    if leaderboard:
        leaderboard_sorted = sorted(leaderboard, key=lambda x: x[1], reverse=True)
        comp = leaderboard_sorted[len(leaderboard_sorted) // 2][0]
    comp_txt = f"Olha aí… até **{comp}** tá mais seguro no KDR." if comp else "Tá difícil hoje."
    return (
        f"💀 **Resumo:** {player_name} tá apanhando. KDR {kdr:.2f} (média do grupo ~{avg_kdr:.2f}).\n"
        f"ADR {adr:.0f}, WR {wr:.0f}%, FK {fk:.2f}. {comp_txt}\n"
        + (f"Contexto: {context}" if context else "")
    ).strip()


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, members_path: str = "members.json"):
        self.bot = bot
        self.members_path = members_path
        self.vintao_local = VintaoLocalStatsHandler()

    @commands.command(name="meu_vintao")
    async def meu_vintao(self, ctx: commands.Context):
        await self.vintao_local.handle(ctx)

    @commands.command(name="stats")
    async def stats(self, ctx: commands.Context, member: discord.Member, month: str = None):
        """
        !stats @Player [YYYY-MM]
        Reads local `players/<gc>/stats-YYYY-MM.json`.
        """
        try:
            members_data = _load_members(self.members_path)
        except Exception as e:
            await ctx.send(f"Erro ao carregar {self.members_path}: {e}")
            return

        did = str(member.id)
        if did not in members_data:
            await ctx.send(f"{member.display_name} não está na lista de membros.")
            return
        gc_id = members_data[did].get("gc")
        if not gc_id:
            await ctx.send(f"{member.display_name} não tem GC ID definido.")
            return
        context_field = members_data[did].get("context", "")

        if month:
            try:
                datetime.strptime(month, "%Y-%m")
                month_year = month
            except ValueError:
                await ctx.send("Use YYYY-MM, ex: `!stats @Player 2025-07`")
                return
        else:
            month_year = datetime.now().strftime("%Y-%m")

        stats_data = _load_stats_file(str(gc_id), month_year)
        if not stats_data:
            await ctx.send(f"Stats de {member.display_name} para {month_year} não disponíveis localmente.")
            return

        embed = discord.Embed(title=f"Stats de {member.display_name} - {month_year}", color=0x00FF00)
        embed.add_field(name="Partidas", value=stats_data.get("total_matches", 0), inline=True)
        embed.add_field(name="Vitórias", value=stats_data.get("total_wins", 0), inline=True)
        embed.add_field(name="Derrotas", value=stats_data.get("total_losses", 0), inline=True)
        embed.add_field(name="Win Rate", value=f"{stats_data.get('overall_win_rate', 0):.2f}%", inline=True)
        embed.add_field(name="Kills", value=stats_data.get("total_kills", 0), inline=True)
        embed.add_field(name="Deaths", value=stats_data.get("total_deaths", 0), inline=True)
        embed.add_field(name="KDR", value=f"{stats_data.get('KDR', 0):.2f}", inline=True)
        embed.add_field(name="ADR", value=f"{stats_data.get('ADR', 0):.2f}", inline=True)
        embed.add_field(name="First Kills", value=stats_data.get("total_first_kills", 0), inline=True)
        embed.add_field(
            name="Avg FK/Match", value=f"{stats_data.get('average_first_kills_per_match', 0):.2f}", inline=True
        )
        embed.add_field(name="HS%", value=f"{stats_data.get('HS_percent', 0):.2f}%", inline=True)

        per_map_data = stats_data.get("per_map", {})
        if per_map_data:
            map_lines = []
            for map_name, mstats in per_map_data.items():
                map_lines.append(
                    f"{map_name}: WR {mstats.get('win_rate', 0):.0f}% | KDR {mstats.get('kdr', 0):.2f} | ADR {mstats.get('adr', 0):.0f} ({mstats.get('matches', 0)} jogos)"
                )
            embed.add_field(name="Por mapa", value="```" + "\n".join(map_lines[:25]) + "```", inline=False)

        # Build small leaderboard by KDR (same month)
        leaderboard: List[Tuple[str, float]] = []
        for did2, info in members_data.items():
            gc2 = info.get("gc")
            if not gc2 or str(gc2) == str(gc_id):
                continue
            other = _load_stats_file(str(gc2), month_year)
            if not other:
                continue
            leaderboard.append((info.get("nickname", "Unknown"), float(other.get("KDR", 0) or 0)))

        summary = generate_local_summary(stats_data, member.display_name, leaderboard, context_field)
        embed.add_field(name="Resumo", value=summary[:1024], inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="alltimestats")
    async def alltimestats(self, ctx: commands.Context, member: discord.Member):
        """
        !alltimestats @Player
        Aggregates all local stats files `players/<gc>/stats-*.json`.
        """
        try:
            members_data = _load_members(self.members_path)
        except Exception as e:
            await ctx.send(f"Erro ao carregar {self.members_path}: {e}")
            return

        did = str(member.id)
        if did not in members_data:
            await ctx.send(f"{member.display_name} não está na lista de membros.")
            return
        gc_id = members_data[did].get("gc")
        if not gc_id:
            await ctx.send(f"{member.display_name} não tem GC ID definido.")
            return

        files = _all_stats_files(str(gc_id))
        if not files:
            await ctx.send(f"Nenhum stats encontrado localmente para {member.display_name}.")
            return

        total_matches = total_wins = total_losses = 0
        total_kills = total_deaths = total_first_kills = 0
        sum_adr = sum_hs = sum_matches_for_avg = 0

        for p in files:
            try:
                stats_data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            matches = int(stats_data.get("total_matches", 0) or 0)
            total_matches += matches
            total_wins += int(stats_data.get("total_wins", 0) or 0)
            total_losses += int(stats_data.get("total_losses", 0) or 0)
            total_kills += int(stats_data.get("total_kills", 0) or 0)
            total_deaths += int(stats_data.get("total_deaths", 0) or 0)
            total_first_kills += int(stats_data.get("total_first_kills", 0) or 0)
            if matches > 0:
                sum_adr += float(stats_data.get("ADR", 0) or 0) * matches
                sum_hs += float(stats_data.get("HS_percent", 0) or 0) * matches
                sum_matches_for_avg += matches

        win_rate = (total_wins / total_matches * 100) if total_matches else 0
        kdr = (total_kills / total_deaths) if total_deaths else float(total_kills)
        avg_adr = (sum_adr / sum_matches_for_avg) if sum_matches_for_avg else 0
        avg_hs = (sum_hs / sum_matches_for_avg) if sum_matches_for_avg else 0
        avg_fk = (total_first_kills / total_matches) if total_matches else 0

        embed = discord.Embed(title=f"All Time Stats de {member.display_name}", color=0x00FF00)
        embed.add_field(name="Partidas", value=total_matches, inline=True)
        embed.add_field(name="Vitórias", value=total_wins, inline=True)
        embed.add_field(name="Derrotas", value=total_losses, inline=True)
        embed.add_field(name="Win Rate", value=f"{win_rate:.2f}%", inline=True)
        embed.add_field(name="Kills", value=total_kills, inline=True)
        embed.add_field(name="Deaths", value=total_deaths, inline=True)
        embed.add_field(name="KDR", value=f"{kdr:.2f}", inline=True)
        embed.add_field(name="ADR", value=f"{avg_adr:.2f}", inline=True)
        embed.add_field(name="HS%", value=f"{avg_hs:.2f}%", inline=True)
        embed.add_field(name="First Kills", value=total_first_kills, inline=True)
        embed.add_field(name="Avg FK/Match", value=f"{avg_fk:.2f}", inline=True)
        await ctx.send(embed=embed)


