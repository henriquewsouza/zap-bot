# vintao_local_stats_handler.py
# ALL‑TIME Ranked Pro do LKS com logging detalhado

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID        = "859273"
PLAYER_NAME  = "LKS"

BASE_DIR    = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "ranked_pro_matches" / GC_ID
MATCHES_DIR = BASE_DIR / "matches"

log = logging.getLogger("VintaoLocal")


class VintaoLocalStatsHandler:
    """Agrupa todos os stats de Ranked Pro do LKS usando arquivos locais."""

    # ---------- helpers ----------
    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    # ---------- coleta IDs ----------
    def _ranked_pro_ids(self) -> set[str]:
        ids: set[str] = set()
        if not HISTORY_DIR.is_dir():
            log.debug("HISTORY_DIR não existe: %s", HISTORY_DIR)
            return ids

        files = list(HISTORY_DIR.glob("*.json"))
        log.debug("Encontrados %d arquivos de histórico em %s", len(files), HISTORY_DIR)

        for f in files:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for m in data:
                    mid = m.get("id")
                    if mid:
                        ids.add(str(mid))
            except Exception as e:
                log.debug("Falha lendo %s: %s", f.name, e)
        log.debug("Total de IDs Ranked Pro coletados: %d", len(ids))
        return ids

    # ---------- agregação ----------
    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_pro_ids()
        if not ids:
            log.debug("Nenhum ID coletado – abortando agregação.")
            return None

        tot = dict(matches=0, wins=0, kills=0, deaths=0,
                   damage=0, rounds=0, firstk=0, hs=0)

        missing_files = 0
        for mid in ids:
            f = MATCHES_DIR / f"{mid}.json"
            if not f.is_file():
                missing_files += 1
                continue

            try:
                m = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                log.debug("Erro parseando %s: %s", f.name, e)
                continue

            jogos   = m.get("jogos", {})
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
                log.debug("ID %s: LKS não encontrado nos players.", mid)
                continue

            # soma
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

        log.debug("Arquivos de match ausentes: %d", missing_files)
        log.debug("Partidas agregadas: %d", tot["matches"])

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
        log.debug("---------- !meu_vintao chamado ----------")
        log.debug("BASE_DIR=%s", BASE_DIR)
        log.debug("HISTORY_DIR=%s", HISTORY_DIR)
        log.debug("MATCHES_DIR=%s", MATCHES_DIR)

        stats = self._aggregate()
        if not stats:
            await ctx.send(f"Nenhuma partida Ranked Pro localizada para {PLAYER_NAME}.")
            return

        em = discord.Embed(
            title=f"{PLAYER_NAME} – Ranked Pro (ALL‑TIME, dados locais)",
            color=0xF1C40F,
        )
        for label, val in (
            ("Partidas",   stats["matches"]),
            ("Vitórias",   stats["wins"]),
            ("Derrotas",   stats["losses"]),
            ("Win Rate",   f"{stats['wr']:.2f}%"),
            ("Kills",      stats["kills"]),
            ("Deaths",     stats["deaths"]),
            ("KDR",        f"{stats['kdr']:.2f}"),
            ("ADR",        f"{stats['adr']:.2f}"),
            ("First Kills", stats["firstk"]),
            ("Avg FK/Match", f"{stats['fk_avg']:.2f}"),
            ("HS %",       f"{stats['hs_pct']:.2f}%"),
        ):
            em.add_field(name=label, value=val, inline=True)

        em.set_footer(text=datetime.utcnow().strftime("Gerado em %d/%m/%Y %H:%M UTC"))
        await ctx.send(embed=em)
