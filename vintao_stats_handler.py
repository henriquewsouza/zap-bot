# vintao_local_stats_handler.py
# ALL‑TIME Ranked Pro do LKS – com mensagem especial

import json, logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID        = "859273"
PLAYER_NAME  = "LKS"

BASE_DIR    = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "ranked_pro_matches" / GC_ID
MATCHES_DIR = BASE_DIR / "match_stats"        / GC_ID

log = logging.getLogger("VintaoLocal")


class VintaoLocalStatsHandler:
    """Agrupa stats Ranked Pro do LKS (arquivos locais) + mensagenzinha."""

    # ------------- helpers -------------
    @staticmethod
    def _safe_int(v) -> int:
        try:   return int(v)
        except Exception: return 0

    # ---------- coleta IDs ----------
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

    # ---------- agregação ----------
    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_pro_ids()
        if not ids:
            return None

        tot = dict(matches=0, wins=0, kills=0, deaths=0,
                   damage=0, rounds=0, firstk=0, hs=0,
                   andz=0)                       # ← contador de “team andZ”

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

            # nomes dos times para checar “andz”
            team_a_name = str(jogos.get("teamNameA", jogos.get("team_name_a", ""))).lower()
            team_b_name = str(jogos.get("teamNameB", jogos.get("team_name_b", ""))).lower()
            if "andz" in team_a_name or "andz" in team_b_name:
                tot["andz"] += 1

            my_rec, my_team = None, None
            for t in ("team_a", "team_b"):
                for p in players.get(t, []):
                    if str(p.get("idplayer")) == GC_ID:
                        my_rec, my_team = p, t
                        break
                if my_rec: break
            if not my_rec:
                continue

            tot["matches"] += 1
            tot["kills"]   += self._safe_int(my_rec.get("nb_kill"))
            tot["deaths"]  += self._safe_int(my_rec.get("death"))
            tot["damage"]  += self._safe_int(my_rec.get("damage"))
            tot["rounds"]  += self._safe_int(my_rec.get("rounds_played"))
            tot["firstk"]  += self._safe_int(my_rec.get("firstkill"))
            tot["hs"]      += self._safe_int(my_rec.get("hs"))

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
            losses = tot["matches"] - tot["wins"],
            kdr    = tot["kills"] / deaths,
            adr    = tot["damage"] / rounds,
            wr     = tot["wins"] / tot["matches"] * 100,
            fk_avg = tot["firstk"] / tot["matches"],
            hs_pct = (tot["hs"] / tot["kills"] * 100) if tot["kills"] else 0,
        )
        return tot

    # ---------- comando ----------
    async def handle(self, ctx: commands.Context):
        stats = self._aggregate()
        if not stats:
            await ctx.send(f"Nenhuma partida Ranked Pro localizada para {PLAYER_NAME}.")
            return

        # ---- mensagem especial ----
        msg_top = (
            "**Êeeeeeeeeee meu vintão!**\n"
            "Uma verdadeira máquina — ainda bem que CS não é jogo de matar, né?\n"
        )
        obs = (
            f"*Observação:* Esse tal de **team andZ** apareceu em "
            f"**{stats['andz']}** partidas… deve ser uma **pá‑carregadeira** mesmo! 🛠️"
        )

        embed = discord.Embed(
            description=msg_top,
            color=0xF1C40F,
            title=f"{PLAYER_NAME} – Ranked Pro + Qualify (ALL‑TIME)"
        )
        # stats
        embed.add_field(name="Partidas",   value=stats["matches"], inline=True)
        embed.add_field(name="K/D Ratio",  value=f"{stats['kdr']:.2f}", inline=True)
        embed.add_field(name="ADR",        value=f"{stats['adr']:.2f}", inline=True)
        embed.add_field(name="Win Rate",   value=f"{stats['wr']:.2f} %", inline=True)
        embed.set_footer(text=obs + f"\nGerado em {datetime.utcnow():%d/%m/%Y %H:%M UTC}")

        await ctx.send(embed=embed)
