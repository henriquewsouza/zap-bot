# ranking_mix_handler.py
import json
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
    MIN_MATCHES_PER_PLAYER     = 3       # descarta player com menos de 3 partidas

    def __init__(
        self,
        s3_client,
        bucket_name: str,
        members_key: str = "members.json",
        matches_prefix: str = "matches/",
        max_workers: int = 10,
    ):
        self.s3 = s3_client
        self.bucket = bucket_name
        self.members_key = members_key
        self.matches_prefix = matches_prefix
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    # ──────────────────────────────────────────────────────────────────────────
    async def handle(self, ctx: commands.Context, args: Optional[str] = None):
        # ------------------------------------------------------------------ 1. FLAGS
        period: Optional[str] = None        # só filtra se for passado
        last_n = 10                         # default
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
            else:
                # qualquer token restante tratamos como possível período YYYY-MM
                try:
                    datetime.strptime(tok, "%Y-%m")
                    period = tok
                except ValueError:
                    await ctx.send("Período inválido – use `YYYY-MM` ou omita para all‑time.")
                    return
                idx += 1

        # ------------------------------------------------------------------ 2. MEMBERS
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=self.members_key)
            members: Dict[str, Any] = json.loads(resp["Body"].read().decode())
        except Exception as exc:
            await ctx.send(f"Erro ao carregar members.json: {exc}")
            return

        discord_to_gc = {did: str(info["gc"]) for did, info in members.items() if info.get("gc")}
        gc_to_nick = {str(info["gc"]): info.get("nickname", f"Unknown({info['gc']})")
                      for info in members.values() if info.get("gc")}
        group_gc_ids = set(discord_to_gc.values())

        if not group_gc_ids:
            await ctx.send("Nenhum GC ID do grupo encontrado.")
            return

        # ------------------------------------------------------------------ 3. LISTA DE PARTIDAS
        try:
            objs = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=self.matches_prefix)
            match_keys = [o["Key"] for o in objs.get("Contents", [])]
        except Exception as exc:
            await ctx.send(f"Erro ao listar partidas no S3: {exc}")
            return

        # ------------------------------------------------------------------ 4. DOWNLOAD EM PARALELO
        loop = asyncio.get_event_loop()

        async def fetch(key: str):
            try:
                data = await loop.run_in_executor(
                    self.executor,
                    lambda: self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode(),
                )
                return key, json.loads(data)
            except Exception:
                return key, None

        fetched = await asyncio.gather(*(fetch(k) for k in match_keys))

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
            if len(recs) < self.MIN_MATCHES_PER_PLAYER:
                continue

            # usa apenas os N últimos jogos do próprio player
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
            await ctx.send("Nenhum player com partidas suficientes para ranquear.")
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

        await ctx.send(embed=embed)
