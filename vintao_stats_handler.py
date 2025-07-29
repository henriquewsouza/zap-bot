# vintao_local_stats_handler.py
# LKS – Ranked Pro + Qualify (ALL‑TIME) • Embed colorido + ZIP embaixo + votação

import json, logging, hashlib, shutil, tempfile
from pathlib import Path
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID       = "859273"
PLAYER_NAME = "LKS"
ANDZ_FIXED  = 71

BASE_DIR = Path(__file__).resolve().parent
HIST_DIR = BASE_DIR / "ranked_pro_matches" / GC_ID
STAT_DIR = BASE_DIR / "match_stats"        / GC_ID

log = logging.getLogger("VintaoLocal")

class VintaoLocalStatsHandler:
    # ---------- helpers ----------
    @staticmethod
    def _safe(v):  # int seguro
        try:
            return int(v)
        except Exception:
            return 0

    def _ranked_ids(self) -> set[str]:
        out = set()
        for f in HIST_DIR.glob("*.json"):
            try:
                out |= {str(m["id"]) for m in json.loads(f.read_text()) if "id" in m}
            except Exception:
                pass
        return out

    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_ids()
        if not ids:
            return None

        tot = dict(matches=0, wins=0, kills=0, deaths=0, damage=0, rounds=0)
        for mid in ids:
            p = STAT_DIR / f"{mid}.json"
            if not p.is_file():
                continue
            try:
                m = json.loads(p.read_text())
            except Exception:
                continue

            jogos   = m.get("jogos", {})
            players = jogos.get("players", {})

            me, team = None, None
            for t in ("team_a", "team_b"):
                for pl in players.get(t, []):
                    if str(pl.get("idplayer")) == GC_ID:
                        me, team = pl, t
                        break
                if me:
                    break
            if not me:
                continue

            tot["matches"] += 1
            tot["kills"]   += self._safe(me.get("nb_kill"))
            tot["deaths"]  += self._safe(me.get("death"))
            tot["damage"]  += self._safe(me.get("damage"))
            tot["rounds"]  += self._safe(me.get("rounds_played"))

            winner = "team_a" if int(jogos.get("score_a", 0)) > int(jogos.get("score_b", 0)) else "team_b"
            if winner == team:
                tot["wins"] += 1

        if not tot["matches"]:
            return None

        deaths  = tot["deaths"] or 1
        rounds  = tot["rounds"] or 1
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
            await ctx.send("Nenhuma partida Ranked Pro encontrada.")
            return

        # descrição do embed
        desc = (
            "**Êeeeeeeeeee meu vintão!**\n"
            "> Uma verdadeira máquina, ainda bem que CS não é jogo de matar, né?\n\n"
            f"• 🕹️ **Partidas:** {stats['matches']}\n"
            f"• 🔫 **K/D Ratio:** {stats['kdr']:.2f} 😂\n"
            f"• 💥 **ADR:** {stats['adr']:.2f}\n"
            f"• 🏆 **Win Rate:** {stats['wr']:.2f}% 😢\n\n"
            f"*🚩 Observação curiosa:* Mesmo em rankeds rolou um tal de **“team andZ”** "
            f"em **{ANDZ_FIXED}** jogos… amizade antiga ou carona de level? 😱\n\n"
            "É **true 20** ou n? Vote abaixo!"
        )

        embed = discord.Embed(
            title=f"⚔️  {PLAYER_NAME} — NAS RANKEDS PRO E QUALIFY EINNN",
            description=desc,
            color=0xF1C40F
        )

        # primeiro envia o embed
        sent_msg = await ctx.send(embed=embed)

        # adiciona reações de voto
        try:
            await sent_msg.add_reaction("👍")
            await sent_msg.add_reaction("👎")
        except discord.HTTPException:
            pass

        # gera ZIP em pasta temporária e manda em mensagem separada
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "LKS_match_stats.zip"
            shutil.make_archive(zip_path.with_suffix(""), "zip", STAT_DIR)
            sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()[:12]
            await ctx.send(
                content=f"`stats brutos anexados • sha256:{sha}`",
                file=discord.File(zip_path, "LKS_match_stats.zip")
            )
