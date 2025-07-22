# ranking_mix_handler.py
import json
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional

import discord
from discord.ext import commands
from botocore.exceptions import ClientError   # se você tratar erros específicos do S3

class RankingMixHandler:
    """
    Lê partidas salvas no S3, agrega estatísticas dos jogadores que fazem parte do grupo
    (identificados no members.json) e gera um ranking em embed do Discord.
    """

    def __init__(self, s3_client, bucket_name: str, object_key: str, max_workers: int = 10):
        self.s3 = s3_client
        self.bucket = bucket_name
        self.object_key = object_key           # ex.: "members.json"
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    # ──────────────────────────────────────────────────────────────────────────────
    # Entrada principal chamada pelo comando do bot
    # ──────────────────────────────────────────────────────────────────────────────
    async def handle(self, ctx: commands.Context, args: Optional[str] = None):
        # ------------------------------------------------------------------
        # 1. Parse de flags/argumentos
        #    ‑last N   → considera somente os N últimos jogos de cada player
        #    YYYY‑MM   → filtra partidas de um mês específico
        #    -all      → ignora período (all‑time)
        # ------------------------------------------------------------------
        period: Optional[str] = None
        all_flag = False
        last_n = 10

        tokens = args.split() if args else []
        clean: List[str] = []

        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.lower() in ("-last", "-l") and i + 1 < len(tokens):
                try:
                    last_n = int(tokens[i + 1])
                    i += 2
                    continue
                except ValueError:
                    await ctx.send("`-last` precisa vir acompanhado de um número inteiro.")
                    return
            clean.append(tok)
            i += 1

        if clean:
            if clean[0].lower() == "-all":
                all_flag = True
            else:
                try:
                    datetime.strptime(clean[0], "%Y-%m")
                    period = clean[0]
                except ValueError:
                    await ctx.send("Período inválido – use no formato `YYYY-MM` ou `-all`.")
                    return

        month_year = None if all_flag else (period or datetime.now().strftime("%Y-%m"))

        # ------------------------------------------------------------------
        # 2. Carrega members.json (Discord ID → GC ID)
        # ------------------------------------------------------------------
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=self.object_key)
            members: Dict[str, Any] = json.loads(resp["Body"].read().decode())
        except Exception as exc:
            await ctx.send(f"Erro ao carregar members.json: {exc}")
            return

        discord_to_gc = {did: str(info.get("gc")) for did, info in members.items() if info.get("gc")}
        gc_to_nick = {str(info.get("gc")): info.get("nickname", f"Unknown({info.get('gc')})")
                      for info in members.values() if info.get("gc")}

        if not discord_to_gc:
            await ctx.send("Nenhum GC ID encontrado em members.json.")
            return

        # ------------------------------------------------------------------
        # 3. Lista arquivos de partidas no S3 (prefixo matches/)
        # ------------------------------------------------------------------
        try:
            list_resp = self.s3.list_objects_v2(Bucket=self.bucket, Prefix="matches/")
            keys = [o["Key"] for o in list_resp.get("Contents", [])]
        except Exception as exc:
            await ctx.send(f"Erro ao listar partidas no S3: {exc}")
            return

        # ------------------------------------------------------------------
        # 4. Faz download das partidas em paralelo
        # ------------------------------------------------------------------
        loop = asyncio.get_event_loop()

        async def fetch(key: str):
            try:
                data = await loop.run_in_executor(
                    self.executor,
                    lambda: self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode()
                )
                return key, json.loads(data)
            except Exception:
                return key, None

        fetched = await asyncio.gather(*(fetch(k) for k in keys))

        # ------------------------------------------------------------------
        # 5. Coleta estatísticas por jogador
        # ------------------------------------------------------------------
        records: Dict[str, List[Dict[str, Any]]] = {}
        seen = set()

        for key, match in fetched:
            if not match:
                continue

            date_str = match.get("data") or match.get("date")
            match_date: Optional[datetime] = None
            if date_str:
                try:
                    match_date = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                except ValueError:
                    pass

            if month_year and (not match_date or match_date.strftime("%Y-%m") != month_year):
                continue

            mid = str(match.get("id") or match.get("match_id") or key.split("/")[-1])
            if mid in seen:
                continue
            seen.add(mid)

            jogos = match.get("jogos", {})
            players = jogos.get("players", {})
            try:
                score_a = int(jogos.get("score_a", 0))
                score_b = int(jogos.get("score_b", 0))
            except (TypeError, ValueError):
                score_a = score_b = 0

            winner = None
            if score_a > score_b:
                winner = "team_a"
            elif score_b > score_a:
                winner = "team_b"

            def record_player(p: Dict[str, Any], team: str):
                gc = str(p.get("idplayer"))
                if gc not in discord_to_gc.values():
                    return
                records.setdefault(gc, []).append({
                    "date": match_date or datetime.min,
                    "kills": int(p.get("nb_kill", 0)),
                    "deaths": int(p.get("death", 0)),
                    "damage": int(p.get("damage", 0)),
                    "rounds": int(p.get("rounds_played", 0)),
                    "first_kills": int(p.get("firstkill", 0)),
                    "win": 1 if winner == team else 0,
                })

            for p in players.get("team_a", []):
                record_player(p, "team_a")
            for p in players.get("team_b", []):
                record_player(p, "team_b")

        # ------------------------------------------------------------------
        # 6. Agrega e calcula métricas (KDR, ADR, Avg FK, Win Rate)
        # ------------------------------------------------------------------
        stats_list: List[Dict[str, Any]] = []
        for gc, recs in records.items():
            if len(recs) < 3:
                continue                          # pouca amostragem

            recs = sorted(recs, key=lambda r: r["date"])[-last_n:]
            if not recs:
                continue

            tot = len(recs)
            summ = {k: sum(r[k] for r in recs)
                    for k in ("kills", "deaths", "damage", "rounds", "first_kills", "win")}

            kdr = summ["kills"] / summ["deaths"] if summ["deaths"] else float(summ["kills"])
            adr = summ["damage"] / summ["rounds"] if summ["rounds"] else 0.0
            avg_fk = summ["first_kills"] / tot
            wr = summ["win"] / tot * 100

            stats_list.append({
                "nick": gc_to_nick.get(gc, gc),
                "kdr": kdr,
                "adr": adr,
                "avg_fk": avg_fk,
                "win_rate": wr,
                "m": tot,
            })

        if not stats_list:
            await ctx.send("Nenhuma partida de mix encontrada para os critérios informados.")
            return

        # ------------------------------------------------------------------
        # 7. Ordena cada métrica para o ranking
        # ------------------------------------------------------------------
        sorted_stats = {
            "KDR":      sorted(stats_list, key=lambda x: x["kdr"],      reverse=True),
            "ADR":      sorted(stats_list, key=lambda x: x["adr"],      reverse=True),
            "Avg FK":   sorted(stats_list, key=lambda x: x["avg_fk"],   reverse=True),
            "Win Rate": sorted(stats_list, key=lambda x: x["win_rate"], reverse=True),
        }

        # Helper para montar bloco de texto
        def build(lst: List[Dict[str, Any]], metric_key: str, label: str) -> str:
            return "\n".join(
                f"{idx+1}. {player['nick']} - {label}: {player[metric_key]:.2f} ({player['m']} jogos)"
                for idx, player in enumerate(lst)
            )

        key_map = {
            "KDR":      "kdr",
            "ADR":      "adr",
            "Avg FK":   "avg_fk",
            "Win Rate": "win_rate",
        }

        # ------------------------------------------------------------------
        # 8. Cria embed e envia ao Discord
        # ------------------------------------------------------------------
        title = f"Mix Ranking {'All‑Time' if all_flag else month_year} (últimos {last_n})"
        embed = discord.Embed(
            title=title,
            description=f"Considerando os últimos {last_n} jogos de cada player",
            color=0x9B59B6,
        )

        for lbl, lst in sorted_stats.items():
            embed.add_field(
                name=lbl,
                value=f"```{build(lst, key_map[lbl], lbl)}```",
                inline=False,
            )

        await ctx.send(embed=embed)
