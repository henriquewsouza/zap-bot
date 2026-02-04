# ranking_mix_handler.py
import json
import os
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional

import discord
from discord.ext import commands


class RankingMixHandler:
    """
    Ranking de mixes onde o grupo joga contra ele mesmo.

    • Partida só conta se cada time tiver ≥1 player do grupo e, somados, ≥8.
    • Por jogador consideramos os N últimos jogos (flag -last, default 10).
    • Filtragem por período (YYYY-MM) só acontece quando passado explicitamente.
    """

    MIN_GROUP_PLAYERS_IN_MATCH = 7       # players do grupo (somando os dois times)
    MIN_MATCHES_PER_PLAYER     = 4       # descarta player com menos de 4 partidas (current month)
    MIN_MATCHES_ALL_TIME       = 10      # descarta player com menos de 20 partidas (all-time)

    def __init__(
        self,
        members_path: str = "members.json",
        matches_dir: str = "matches",
        max_workers: int = 10,
    ):
        self.members_path = members_path
        self.matches_dir = matches_dir
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    # ──────────────────────────────────────────────────────────────────────────
    async def handle(self, ctx: commands.Context, args: Optional[str] = None):
        # ------------------------------------------------------------------ 1. FLAGS
        period: Optional[str] = None  # default to all-time
        last_n = 10                   # default
        toks = args.split() if args else []

        idx = 0
        while idx < len(toks):
            tok = toks[idx]
            if tok.lower() in ("-last", "-l") and idx + 1 < len(toks):
                try:
                    last_n = int(toks[idx + 1])
                    idx += 2
                    continue
                except ValueError:
                    await ctx.send("`-last` precisa ser seguido por número inteiro.")
                    return
            elif tok.lower() == "-all":
                period = None  # all-time
                idx += 1
            else:
                # qualquer token restante tratamos como possível período YYYY-MM
                try:
                    datetime.strptime(tok, "%Y-%m")
                    period = tok
                except ValueError:
                    await ctx.send("Período inválido – use `YYYY-MM`, `-all` para all-time, ou omita para all-time.")
                    return
                idx += 1

        # ------------------------------------------------------------------ 2. MEMBERS (LOCAL)
        try:
            with open(self.members_path, "r", encoding="utf-8") as f:
                members: Dict[str, Any] = json.load(f)
        except Exception as exc:
            await ctx.send(f"Erro ao carregar {self.members_path}: {exc}")
            return

        discord_to_gc = {did: str(info["gc"]) for did, info in members.items() if info.get("gc")}
        gc_to_nick = {str(info["gc"]): info.get("nickname", f"Unknown({info['gc']})")
                      for info in members.values() if info.get("gc")}
        group_gc_ids = set(discord_to_gc.values())

        if not group_gc_ids:
            await ctx.send("Nenhum GC ID do grupo encontrado.")
            return

        # ------------------------------------------------------------------ 3. LISTA DE PARTIDAS (LOCAL)
        matches_dir = self.matches_dir
        if not os.path.exists(matches_dir):
            await ctx.send("Pasta de partidas local não encontrada.")
            return
        
        match_files = [f for f in os.listdir(matches_dir) if f.endswith('.json')]
        if not match_files:
            await ctx.send("Nenhuma partida encontrada na pasta local.")
            return

        # ------------------------------------------------------------------ 4. PROCESSAR ARQUIVOS LOCAIS
        fetched = []
        for filename in match_files:
            filepath = os.path.join(matches_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fetched.append((filename, data))
            except Exception:
                fetched.append((filename, None))

        # ------------------------------------------------------------------ 5. AGREGAÇÃO
        stats: Dict[str, List[Dict[str, Any]]] = {}   # gc_id -> lista de registros
        processed = set()

        for key, match in fetched:
            if not match:
                continue

            # (a) filtro de período – só se usuário passou
            if period:
                ds = match.get("data") or match.get("date")
                try:
                    md = datetime.strptime(ds, "%d/%m/%Y %H:%M")
                except Exception:
                    continue
                if md.strftime("%Y-%m") != period:
                    continue
            else:
                ds = match.get("data") or match.get("date")
                try:
                    md = datetime.strptime(ds, "%d/%m/%Y %H:%M")
                except Exception:
                    md = None  # se não vier data usa mínima

            # (b) evita duplicidade
            match_id = str(match.get("id") or match.get("match_id") or key.split("/")[-1])
            if match_id in processed:
                continue
            processed.add(match_id)

            # (c) estrutura / players grupo
            jogos = match.get("jogos", {})
            players_info = jogos.get("players", {})
            team_a = players_info.get("team_a", [])
            team_b = players_info.get("team_b", [])

            grp_a = [p for p in team_a if str(p.get("idplayer")) in group_gc_ids]
            grp_b = [p for p in team_b if str(p.get("idplayer")) in group_gc_ids]

            if not grp_a or not grp_b or (len(grp_a) + len(grp_b) < self.MIN_GROUP_PLAYERS_IN_MATCH):
                continue

            # (d) vencedor
            try:
                sa = int(jogos.get("score_a", 0)); sb = int(jogos.get("score_b", 0))
            except Exception:
                sa = sb = 0
            winner = "team_a" if sa > sb else "team_b" if sb > sa else None

            # (e) acumula registro por player
            def add(p: Dict[str, Any], team: str):
                gc = str(p.get("idplayer"))
                stats.setdefault(gc, []).append({
                    "date": md or datetime.min,
                    "kills": int(p.get("nb_kill", 0)),
                    "deaths": int(p.get("death", 0)),
                    "damage": int(p.get("damage", 0)),
                    "rounds": int(p.get("rounds_played", 0)),
                    "first_kills": int(p.get("firstkill", 0)),
                    "win": 1 if winner == team else 0,
                })

            for p in grp_a:
                add(p, "team_a")
            for p in grp_b:
                add(p, "team_b")

        # ------------------------------------------------------------------ 6. MÉTRICAS POR PLAYER
        players: List[Dict[str, Any]] = []
        for gc, recs in stats.items():
            # Apply different minimum matches based on period
            # All-time (period=None): 20+ matches, Current month: 4+ matches
            min_matches = self.MIN_MATCHES_ALL_TIME if period is None else self.MIN_MATCHES_PER_PLAYER
            if len(recs) < min_matches:
                continue

            # usa apenas os N últimos jogos do próprio player
            # Se -all foi usado, não limita por last_n
            if period is None and "-all" in (args or ""):
                # Para -all, usa todos os matches (não limita por last_n)
                pass
            else:
                # Para outros casos, limita por last_n
                recs = sorted(recs, key=lambda r: r["date"])[-last_n:]

            tot = len(recs)
            S = {k: sum(r[k] for r in recs) for k in
                 ("kills", "deaths", "damage", "rounds", "first_kills", "win")}

            players.append({
                "nick": gc_to_nick.get(gc, f"Unknown({gc})"),
                "matches": tot,
                "kdr": S["kills"] / S["deaths"] if S["deaths"] else S["kills"],
                "adr": S["damage"] / S["rounds"] if S["rounds"] else 0,
                "avg_fk": S["first_kills"] / tot,
                "win_rate": (S["win"] / tot) * 100,
            })

        if not players:
            if period is None:
                await ctx.send("Nenhum player encontrado com pelo menos 20 partidas para ranking all-time.")
            else:
                await ctx.send(f"Nenhum player encontrado com pelo menos 4 partidas para ranking de {period}.")
            return

        # ------------------------------------------------------------------ 7. RANKINGS
        ranks = {
            "KDR":      sorted(players, key=lambda p: p["kdr"],      reverse=True),
            "ADR":      sorted(players, key=lambda p: p["adr"],      reverse=True),
            "Avg FK":   sorted(players, key=lambda p: p["avg_fk"],   reverse=True),
            "Win Rate": sorted(players, key=lambda p: p["win_rate"], reverse=True),
        }
        key_of = {"KDR": "kdr", "ADR": "adr", "Avg FK": "avg_fk", "Win Rate": "win_rate"}

        def build(lst: List[Dict[str, Any]], k: str, label: str) -> str:
            return "\n".join(
                f"{i+1}. {p['nick']} - {label}: {p[k]:.2f} ({p['matches']} jogos)"
                for i, p in enumerate(lst)
            )

        # ------------------------------------------------------------------ 8. EMBED
        title = f"Mix Ranking {'All‑Time' if not period else period} (últ. {last_n})"
        embed = discord.Embed(
            title=title,
            description=f"Somente partidas grupo vs grupo (≥{self.MIN_GROUP_PLAYERS_IN_MATCH} players do grupo).",
            color=0x9B59B6,
        )
        for lbl, lst in ranks.items():
            embed.add_field(name=lbl, value=f"```{build(lst, key_of[lbl], lbl)}```", inline=False)

        # Send as separate messages to avoid Discord limits
        if period is None and "-all" in (args or ""):
            title = f"🎮 **Mix Ranking All‑Time**"
        elif period is None:
            title = f"🎮 **Mix Ranking All‑Time (últ. {last_n})**"
        else:
            title = f"🎮 **Mix Ranking {period} (últ. {last_n})**"
        description = f"Somente partidas grupo vs grupo (≥{self.MIN_GROUP_PLAYERS_IN_MATCH} players do grupo)."
        
        await ctx.send(f"{title}\n{description}")
        
        for lbl, lst in ranks.items():
            await ctx.send(f"**{lbl} Ranking:**\n```{build(lst, key_of[lbl], lbl)}```")
