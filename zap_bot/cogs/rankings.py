from __future__ import annotations

import json
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands

from ranking_creator_handler import RankingCreatorHandler
from ranking_handler import RankingHandler
from ranking_mix_handler import RankingMixHandler

from ..levels import LevelService
from ..team_balance import build_team_message, generate_partitions


def _load_members(members_path: str = "members.json") -> Dict[str, Any]:
    with open(members_path, "r", encoding="utf-8") as f:
        return json.load(f)


class RankingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot, levels: LevelService, members_path: str = "members.json"):
        self.bot = bot
        self.levels = levels
        self.members_path = members_path
        self.ranking_handler = RankingHandler(members_path=members_path, matches_dir="matches")
        self.ranking_mix_handler = RankingMixHandler(members_path=members_path, matches_dir="matches")
        self.creator_handler = RankingCreatorHandler(members_path=members_path, matches_dir="matches")

    @commands.command(name="ranking")
    async def ranking(self, ctx: commands.Context, *, args: str = None):
        # keep existing behavior from handler (local-only now)
        await self.ranking_handler.handle(ctx, args)

    @commands.command(name="ranking_mix")
    async def ranking_mix(self, ctx: commands.Context, *, args: str = None):
        await self.ranking_mix_handler.handle(ctx, args)

    @commands.command(name="ranking_creators")
    async def ranking_creators(self, ctx: commands.Context, *, args: str = None):
        await self.creator_handler.handle(ctx, args)

    @commands.command(name="simulatemix")
    async def simulatemix(self, ctx: commands.Context):
        """
        !simulatemix
        Simula um mix com 10 jogadores aleatórios do members.json (active=true/omisso).
        """
        await ctx.send("🎲 Simulando mix com 10 jogadores aleatórios...")
        try:
            members_data = _load_members(self.members_path)
        except Exception as e:
            await ctx.send(f"Erro ao carregar {self.members_path}: {e}")
            return

        valid_players = []
        for discord_id, info in members_data.items():
            if info.get("nickname") and info.get("level") is not None:
                if info.get("active", True):
                    try:
                        valid_players.append(
                            {
                                "discord_id": int(discord_id),
                                "nickname": info["nickname"],
                                "level": int(info.get("level", 0) or 0),
                            }
                        )
                    except Exception:
                        continue

        if len(valid_players) < 10:
            await ctx.send(f"❌ Não há jogadores suficientes. Encontrados: {len(valid_players)}, necessários: 10")
            return

        selected = random.sample(valid_players, 10)

        class FakeMember:
            def __init__(self, pid: int, name: str):
                self.id = pid
                self.display_name = name

            @property
            def mention(self):
                return f"<@{self.id}>"

        members = [FakeMember(p["discord_id"], p["nickname"]) for p in selected]
        level_by_id = {p["discord_id"]: p["level"] for p in selected}

        partitions = generate_partitions(members, get_level=lambda m: level_by_id.get(m.id, 0))
        if not partitions:
            await ctx.send("❌ Não foi possível gerar times balanceados.")
            return
        best = partitions[0]

        msg = build_team_message(
            best.team1,
            best.team2,
            get_level=lambda m: level_by_id.get(m.id, 0),
            get_mention=lambda m: m.mention,
        )
        await ctx.send("🎮 **MIX SIMULADO BALANCEADO**\n\n" + msg + f"\n\n⚖️ **Diferença:** {best.diff}")

    @commands.command(name="c4")
    async def c4(self, ctx: commands.Context):
        """
        !c4
        Ranking de C4 plantada por rounds jogados (all-time) lendo `matches/`.
        """
        await ctx.send("💣 Calculando ranking de C4 plantada...")
        try:
            members_data = _load_members(self.members_path)
        except Exception as e:
            await ctx.send(f"Erro ao carregar {self.members_path}: {e}")
            return

        gc_to_nickname = {
            str(info.get("gc")): info.get("nickname", f"Unknown({info.get('gc')})")
            for info in members_data.values()
            if info.get("gc")
        }
        group_gc_ids = set(gc_to_nickname.keys())
        if not group_gc_ids:
            await ctx.send("Nenhum GC ID encontrado nos dados dos membros.")
            return

        matches_dir = "matches"
        if not os.path.exists(matches_dir):
            await ctx.send("Pasta `matches/` não encontrada.")
            return

        c4_by_gc: Dict[str, int] = {}
        rounds_by_gc: Dict[str, int] = {}

        for fn in os.listdir(matches_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(matches_dir, fn), "r", encoding="utf-8") as f:
                    match = json.load(f)
            except Exception:
                continue

            jogos = match.get("jogos", {})
            players = jogos.get("players", {})
            for team in ("team_a", "team_b"):
                for p in players.get(team, []):
                    gc = str(p.get("idplayer"))
                    if gc not in group_gc_ids:
                        continue
                    try:
                        planted = int(p.get("c4_plant", 0) or 0)
                        rounds = int(p.get("rounds_played", 0) or 0)
                    except Exception:
                        continue
                    c4_by_gc[gc] = c4_by_gc.get(gc, 0) + planted
                    rounds_by_gc[gc] = rounds_by_gc.get(gc, 0) + rounds

        rows = []
        for gc, planted in c4_by_gc.items():
            rounds = rounds_by_gc.get(gc, 0) or 0
            if rounds <= 0:
                continue
            rows.append((gc, planted / rounds, planted, rounds))
        rows.sort(key=lambda x: x[1], reverse=True)

        if not rows:
            await ctx.send("Nenhum dado de C4 encontrado nos matches locais.")
            return

        text = "\n".join(
            f"{i+1}. {gc_to_nickname.get(gc, gc)} – {rate:.3f} ({planted}/{rounds})"
            for i, (gc, rate, planted, rounds) in enumerate(rows[:25])
        )
        await ctx.send(f"💣 **Ranking C4 (all-time)**\n```{text}```")

    @commands.command(name="arca")
    async def arca(self, ctx: commands.Context, month: str = None):
        """
        !arca [YYYY-MM | -all]
        Agrega performance por mapa lendo `matches/` local.
        """
        all_flag = month == "-all"
        if month and not all_flag:
            try:
                datetime.strptime(month, "%Y-%m")
            except ValueError:
                await ctx.send("Use YYYY-MM ou -all.")
                return
        month_year = month if (month and not all_flag) else datetime.now().strftime("%Y-%m")

        try:
            members_data = _load_members(self.members_path)
        except Exception as e:
            await ctx.send(f"Erro ao carregar {self.members_path}: {e}")
            return

        group_gc_ids = {str(info.get("gc")) for info in members_data.values() if info.get("gc")}
        if not group_gc_ids:
            await ctx.send("No group GC ids found in members data.")
            return

        matches_dir = "matches"
        if not os.path.isdir(matches_dir):
            await ctx.send("Pasta `matches/` não encontrada.")
            return

        def create_bar(percentage, length=10):
            filled_length = int(round(length * percentage / 100))
            return "█" * filled_length + "─" * (length - filled_length)

        group_maps: Dict[str, Dict[str, float]] = {}
        counted = set()

        for fn in os.listdir(matches_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(matches_dir, fn), "r", encoding="utf-8") as f:
                    match_data = json.load(f)
            except Exception:
                continue

            if not all_flag:
                ds = match_data.get("data")
                if not ds:
                    continue
                try:
                    d = datetime.strptime(ds, "%d/%m/%Y %H:%M")
                except Exception:
                    continue
                if d.strftime("%Y-%m") != month_year:
                    continue

            match_id = str(match_data.get("id") or match_data.get("match_id") or fn.replace(".json", ""))
            if match_id in counted:
                continue
            counted.add(match_id)

            jogos = match_data.get("jogos", {})
            map_name = jogos.get("map_name", "unknown")
            players_data = jogos.get("players", {})

            team_group_counts: Dict[str, int] = {}
            team_group_stats: Dict[str, Dict[str, int]] = {}
            for team in ("team_a", "team_b"):
                count = 0
                stats_sum = {"kills": 0, "deaths": 0, "damage": 0, "rounds": 0}
                for p in players_data.get(team, []):
                    if str(p.get("idplayer")) in group_gc_ids:
                        count += 1
                        try:
                            stats_sum["kills"] += int(p.get("nb_kill", 0) or 0)
                            stats_sum["deaths"] += int(p.get("death", 0) or 0)
                            stats_sum["damage"] += int(p.get("damage", 0) or 0)
                            stats_sum["rounds"] += int(p.get("rounds_played", 0) or 0)
                        except Exception:
                            pass
                team_group_counts[team] = count
                team_group_stats[team] = stats_sum

            teams_with_group = [t for t, c in team_group_counts.items() if c > 0]
            if len(teams_with_group) != 1:
                continue
            team = teams_with_group[0]
            if team_group_counts[team] < 3:
                continue

            try:
                score_a = int(jogos.get("score_a", "0"))
                score_b = int(jogos.get("score_b", "0"))
            except Exception:
                score_a = score_b = 0
            winning_team = "team_a" if score_a > score_b else "team_b" if score_b > score_a else None
            win = 1 if winning_team == team else 0

            gm = group_maps.setdefault(
                map_name, {"matches": 0, "wins": 0, "kills": 0, "deaths": 0, "damage": 0, "rounds": 0}
            )
            gm["matches"] += 1
            gm["wins"] += win
            gm["kills"] += team_group_stats[team]["kills"]
            gm["deaths"] += team_group_stats[team]["deaths"]
            gm["damage"] += team_group_stats[team]["damage"]
            gm["rounds"] += team_group_stats[team]["rounds"]

        if not group_maps:
            await ctx.send("Nenhum dado encontrado para o período.")
            return

        lines = []
        for map_name, stats in sorted(group_maps.items(), key=lambda kv: kv[1]["matches"], reverse=True):
            m = stats["matches"] or 1
            wr = stats["wins"] / m * 100
            kdr = stats["kills"] / (stats["deaths"] or 1)
            adr = stats["damage"] / (stats["rounds"] or 1)
            lines.append(f"{map_name:12} WR {wr:5.1f}% {create_bar(wr)} | KDR {kdr:.2f} | ADR {adr:.1f} | {m} jogos")

        title = f"🗺️ **Arca {('All Time' if all_flag else month_year)}**"
        await ctx.send(title + "\n```" + "\n".join(lines[:30]) + "```")


