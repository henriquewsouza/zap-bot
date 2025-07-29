# vintao_local_stats_handler.py
# ALL‑TIME Ranked Pro (“vintão”) do LKS  – dados locais

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID        = "859273"
PLAYER_NAME  = "LKS"
HISTORY_DIR  = Path("ranked_pro_matches") / GC_ID   # onde ficam 859273-*-ranked pro.json
MATCHES_DIR  = Path("matches")                      # stats completos <id>.json


class VintaoLocalStatsHandler:
    """Soma todos os Ranked Pro do LKS a partir dos arquivos locais."""

    # ---------------- helpers ----------------
    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    def _ranked_pro_ids(self) -> set[str]:
        """Coleta IDs de partida a partir dos históricos Ranked Pro."""
        ids: set[str] = set()
        if not HISTORY_DIR.is_dir():
            return ids
        for f in HISTORY_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for m in data:
                    mid = m.get("id")
                    if mid:
                        ids.add(str(mid))
            except Exception:
                continue
        return ids

    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_pro_ids()
        if not ids:
            return None

        tot = {
            "matches": 0, "wins": 0,
            "kills": 0, "deaths": 0, "damage": 0, "rounds": 0,
            "firstk": 0, "hs": 0,
        }

        for mid in ids:
            f = MATCHES_DIR / f"{mid}.json"
            if not f.is_file():
                continue
            try:
                m = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue

            jogos   = m.get("jogos", {})
            players = jogos.get("players", {})

            my_rec = None
            my_team = None
            for team in ("team_a", "team_b"):
                for p in players.get(team, []):
                    if str(p.get("idplayer")) == GC_ID:
                        my_rec, my_team = p, team
                        break
                if my_rec:
                    break
            if not my_rec:
                continue  # LKS não jogou/ausente

            tot["matches"] += 1
            tot["kills"]   += self._safe_int(my_rec.get("nb_kill"))
            tot["deaths"]  += self._safe_int(my_rec.get("death"))
            tot["damage"]  += self._safe_int(my_rec.get("damage"))
            tot["rounds"]  += self._safe_int(my_rec.get("rounds_played"))
            tot["firstk"]  += self._safe_int(my_rec.get("firstkill"))
            tot["hs"]      += self._safe_int(my_rec.get("hs"))

            # vitória
            sa = self._safe_int(jogos.get("score_a"))
            sb = self._safe_int(jogos.get("score_b"))
            winner = "team_a" if sa > sb else "team_b" if sb > sa else None
            if winner and winner == my_team:
                tot["wins"] += 1

        if tot["matches"] == 0:
            return None

        deaths  = tot["deaths"] or 1
        rounds  = tot["rounds"] or 1
        tot.update(
            losses = tot["matches"] - tot["wins"],
            kdr    = tot["kills"] / deaths,
            adr    = tot["damage"] / rounds,
            wr     = tot["wins"] / tot["matches"] * 100,
            fk_avg = tot["firstk"] / tot["matches"],
            hs_pct = (tot["hs"] / tot["kills"] * 100) if tot["kills"] else 0,
        )
        return tot

    # --------------- comando público ---------------
    async def handle(self, ctx: commands.Context):
        stats = self._aggregate()
        if not stats:
            await ctx.send(f"Nenhuma partida Ranked Pro localizada para {PLAYER_NAME}.")
            return

        em = discord.Embed(
            title=f"{PLAYER_NAME} – Ranked Pro (ALL‑TIME)",
            color=0xF1C40F,
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

        em.set_footer(text=datetime.utcnow().strftime("Gerado em %d/%m/%Y %H:%M UTC"))
        await ctx.send(embed=em)
