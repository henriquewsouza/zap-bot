# vintao_stats_handler.py
# Stats ALL‑TIME de Ranked Pro (“vintão”) do LKS – GC 859273
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import discord
from botocore.exceptions import ClientError

GC_ID = "859273"
PLAYER_NAME = "LKS"


class VintaoStatsHandler:
    def __init__(self, s3_client, bucket_name: str):
        self.s3 = s3_client
        self.bucket = bucket_name

    # ───────────────────────── helpers ─────────────────────────
    def _aggregate_all(self) -> Optional[Dict[str, Any]]:
        try:
            objs = self.s3.list_objects_v2(
                Bucket=self.bucket, Prefix="matches/"
            ).get("Contents", [])
        except ClientError:
            logging.exception("Erro listando matches/")
            return None

        tot = {
            "matches": 0, "wins": 0, "kills": 0, "deaths": 0,
            "damage": 0, "rounds": 0, "firstk": 0, "hs": 0,
        }

        for obj in objs:
            try:
                m = json.loads(
                    self.s3.get_object(Bucket=self.bucket, Key=obj["Key"])["Body"]
                    .read().decode("utf-8")
                )
            except Exception:
                continue

            if m.get("type", "").lower() != "ranked pro":
                continue

            jogos = m.get("jogos", {})
            players = jogos.get("players", {})
            my_rec, my_team = None, None
            for team in ("team_a", "team_b"):
                for p in players.get(team, []):
                    if str(p.get("idplayer")) == GC_ID:
                        my_rec, my_team = p, team
                        break
                if my_rec:
                    break
            if not my_rec:
                continue

            # soma stats
            tot["matches"] += 1
            for raw, key in (("nb_kill", "kills"), ("death", "deaths"),
                             ("damage", "damage"), ("rounds_played", "rounds"),
                             ("firstkill", "firstk"), ("hs", "hs")):
                tot[key] += int(my_rec.get(raw, 0))

            # vitória?
            try:
                sa = int(jogos.get("score_a", 0))
                sb = int(jogos.get("score_b", 0))
            except Exception:
                sa = sb = 0
            winner = "team_a" if sa > sb else "team_b" if sb > sa else None
            if winner == my_team:
                tot["wins"] += 1

        if not tot["matches"]:
            return None

        deaths = tot["deaths"]
        rounds = tot["rounds"]
        tot.update({
            "losses": tot["matches"] - tot["wins"],
            "kdr": tot["kills"] / deaths if deaths else tot["kills"],
            "adr": tot["damage"] / rounds if rounds else 0,
            "wr":  tot["wins"] / tot["matches"] * 100,
            "fk_avg": tot["firstk"] / tot["matches"],
            "hs_pct": tot["hs"] / tot["kills"] * 100 if tot["kills"] else 0,
        })
        return tot

    # ───────────────────────── API pública ─────────────────────
    async def handle(self, ctx):
        stats = self._aggregate_all()
        if not stats:
            await ctx.send(f"Nenhuma partida Ranked Pro encontrada para {PLAYER_NAME}.")
            return

        em = discord.Embed(
            title=f"{PLAYER_NAME} – Ranked Pro (ALL‑TIME)",
            color=0xf1c40f,
        )
        for n, v in (
            ("Partidas", stats["matches"]), ("Vitórias", stats["wins"]),
            ("Derrotas", stats["losses"]),  ("Win Rate", f"{stats['wr']:.2f}%"),
            ("Kills", stats["kills"]),      ("Deaths", stats["deaths"]),
            ("KDR", f"{stats['kdr']:.2f}"), ("ADR", f"{stats['adr']:.2f}"),
            ("First Kills", stats["firstk"]), ("Avg FK/Match", f"{stats['fk_avg']:.2f}"),
            ("HS %", f"{stats['hs_pct']:.2f}%"),
        ):
            em.add_field(name=n, value=v, inline=True)

        # timestamp de geração para referência
        em.set_footer(text=datetime.utcnow().strftime("Atualizado em %d/%m/%Y %H:%M UTC"))
        await ctx.send(embed=em)
