# vintao_local_stats_handler.py
# LKS – Ranked Pro + Qualify (ALL‑TIME)  •  Texto “currículo” + ZIP + votos

import json, logging, hashlib, shutil, tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID        = "859273"
PLAYER_NAME  = "LKS"
ANDZ_FIXED   = 71            # contagem manual do “team andZ”

BASE_DIR    = Path(__file__).resolve().parent
HISTORY_DIR = BASE_DIR / "ranked_pro_matches" / GC_ID
MATCHES_DIR = BASE_DIR / "match_stats"        / GC_ID

log = logging.getLogger("VintaoLocal")


class VintaoLocalStatsHandler:
    # ---------- helpers ----------
    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    def _ranked_ids(self) -> set[str]:
        ids = set()
        for f in HISTORY_DIR.glob("*.json"):
            try:
                ids |= {str(m["id"]) for m in json.loads(f.read_text()) if "id" in m}
            except Exception:
                log.debug("Falha lendo %s", f.name)
        return ids

    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_ids()
        if not ids:
            return None

        tot = dict(matches=0, wins=0, kills=0, deaths=0, damage=0, rounds=0)

        for mid in ids:
            p = MATCHES_DIR / f"{mid}.json"
            if not p.is_file():
                continue
            try:
                m = json.loads(p.read_text())
            except Exception:
                continue

            jogos   = m.get("jogos", {})
            players = jogos.get("players", {})

            my, my_team = None, None
            for t in ("team_a", "team_b"):
                for pl in players.get(t, []):
                    if str(pl.get("idplayer")) == GC_ID:
                        my, my_team = pl, t
                        break
                if my: break
            if not my:
                continue

            tot["matches"] += 1
            tot["kills"]   += self._safe_int(my.get("nb_kill"))
            tot["deaths"]  += self._safe_int(my.get("death"))
            tot["damage"]  += self._safe_int(my.get("damage"))
            tot["rounds"]  += self._safe_int(my.get("rounds_played"))

            if ("team_a" if int(jogos.get("score_a", 0)) >
                          int(jogos.get("score_b", 0)) else "team_b") == my_team:
                tot["wins"] += 1

        if not tot["matches"]:
            return None

        deaths = tot["deaths"] or 1
        rounds = tot["rounds"] or 1
        tot.update(
            kdr = tot["kills"] / deaths,
            adr = tot["damage"] / rounds,
            wr  = tot["wins"] / tot["matches"] * 100,
        )
        return tot

    # ---------- comando ----------
    async def handle(self, ctx: commands.Context):
        stats = self._aggregate()
        if not stats:
            await ctx.send("Nenhuma partida encontrada.")
            return

        # ── monta a mensagem estilo “currículo” ─────────────────────────
        msg = (
            f"**⚔️  {PLAYER_NAME} — Ranked Pro + Qualify (ALL‑TIME)**\n\n"
            f"**Êeeeeeeeeee meu vintão!**\n"
            f"> Uma verdadeira máquina — ainda bem que CS não é jogo de matar, né?\n\n"
            f"📊 **Resumo de Performance**\n"
            f"• 🕹️ Partidas: **{stats['matches']}**\n"
            f"• 🔫 K/D Ratio: **{stats['kdr']:.2f}** :KEKW:\n"
            f"• 💥 ADR: **{stats['adr']:.2f}**\n"
            f"• 🏆 Win Rate: **{stats['wr']:.2f}%** :pepecry:\n\n"
            f"*🚩 Observação curiosa:*  \n"
            f"Rolou um tal de **“team andZ”** em **{ANDZ_FIXED}** jogos… "
            f"amizade antiga ou carona de level? 🤔 :shocked:\n\n"
            "É **true 20** ou n? Vote abaixo!"
        )

        # ── cria ZIP temporário + checksum ──────────────────────────────
        with tempfile.TemporaryDirectory() as tmp:
            zip_p = Path(tmp) / "LKS_match_stats.zip"
            shutil.make_archive(zip_p.with_suffix(""), "zip", MATCHES_DIR)
            sha = hashlib.sha256(zip_p.read_bytes()).hexdigest()[:12]

            sent = await ctx.send(
                content=msg + f"\n\n`stats brutos anexados com as provas do CRIME • sha256:{sha}`",
                file=discord.File(zip_p, "LKS_match_stats.zip")
            )

        # ── adiciona reações para votação ───────────────────────────────
        try:
            await sent.add_reaction("👍")  # true 20
            await sent.add_reaction("👎")  # n
        except discord.HTTPException:
            pass
