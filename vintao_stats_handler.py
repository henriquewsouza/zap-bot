# vintao_local_stats_handler.py
# ALL‑TIME Ranked Pro do LKS – mensagem em markdown

import json, logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID        = "859273"
PLAYER_NAME  = "LKS"
FIXED_ANDZ   = 71                    # já contado manualmente

BASE_DIR    = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "ranked_pro_matches" / GC_ID
MATCHES_DIR = BASE_DIR / "match_stats"        / GC_ID

log = logging.getLogger("VintaoLocal")


class VintaoLocalStatsHandler:
    """Soma todos os stats Ranked Pro + Qualify do LKS e manda texto."""

    # ── helpers ───────────────────────────────
    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    def _ranked_pro_ids(self) -> set[str]:
        ids = set()
        for f in HISTORY_DIR.glob("*.json"):
            try:
                for m in json.loads(f.read_text(encoding="utf-8")):
                    if "id" in m:
                        ids.add(str(m["id"]))
            except Exception as e:
                log.debug("Falha lendo %s: %s", f.name, e)
        return ids

    # ── agregação ────────────────────────────
    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_pro_ids()
        if not ids:
            return None

        tot = dict(matches=0, wins=0, kills=0, deaths=0,
                   damage=0, rounds=0)

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

            my, my_team = None, None
            for t in ("team_a", "team_b"):
                for p in players.get(t, []):
                    if str(p.get("idplayer")) == GC_ID:
                        my, my_team = p, t
                        break
                if my:
                    break
            if not my:
                continue

            # soma
            tot["matches"] += 1
            tot["kills"]   += self._safe_int(my.get("nb_kill"))
            tot["deaths"]  += self._safe_int(my.get("death"))
            tot["damage"]  += self._safe_int(my.get("damage"))
            tot["rounds"]  += self._safe_int(my.get("rounds_played"))

            sa = self._safe_int(jogos.get("score_a"))
            sb = self._safe_int(jogos.get("score_b"))
            winner = "team_a" if sa > sb else "team_b" if sb > sa else None
            if winner == my_team:
                tot["wins"] += 1

        if tot["matches"] == 0:
            return None

        deaths  = tot["deaths"] or 1
        rounds  = tot["rounds"] or 1
        tot.update(
            kdr = tot["kills"] / deaths,
            adr = tot["damage"] / rounds,
            wr  = tot["wins"] / tot["matches"] * 100,
        )
        return tot

    # ── comando ───────────────────────────────
    async def handle(self, ctx: commands.Context):
        stats = self._aggregate()
        if not stats:
            await ctx.send(f"Nenhuma partida Ranked Pro localizada para {PLAYER_NAME}.")
            return

        msg = (
            "**Êeeeeeeeeee meu vintão!**  \n"
            "> Uma verdadeira máquina — ainda bem que CS não é jogo de matar, né?\n\n"
            "**Ranked Pro + Qualify (ALL‑TI**
