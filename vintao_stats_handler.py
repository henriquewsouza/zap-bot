# vintao_local_stats_handler.py
# ALL‑TIME Ranked Pro (vintão) do LKS – leitura 100 % local

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

import discord
from discord.ext import commands

GC_ID        = "859273"
PLAYER_NAME  = "LKS"

# -------- diretórios ancorados no local deste arquivo --------
BASE_DIR     = Path(__file__).resolve().parent
HISTORY_DIR  = BASE_DIR / "ranked_pro_matches" / GC_ID
MATCHES_DIR  = BASE_DIR / "matches"
# --------------------------------------------------------------


class VintaoLocalStatsHandler:
    """Agrupa todos os stats de Ranked Pro do LKS usando arquivos locais."""

    # ------------- helpers -------------
    @staticmethod
    def _safe_int(v) -> int:
        try:
            return int(v)
        except Exception:
            return 0

    def _ranked_pro_ids(self) -> set[str]:
        """Lê todos os JSON em HISTORY_DIR e devolve IDs de partidas."""
        ids: set[str] = set()
        if not HISTORY_DIR.is_dir():
            return ids
        for f in HISTORY_DIR.glob("*.json"):
            try:
                for m in json.loads(f.read_text(encoding="utf-8")):
                    mid = m.get("id")
                    if mid:
                        ids.add(str(mid))
            except Exception:
                pass
        return ids

    def _aggregate(self) -> Optional[Dict[str, Any]]:
        ids = self._ranked_pro_ids()
        if not ids:
            return None

        tot = dict(
            matches=0, wins=0, kills=0, deaths=0,
            damage=0, rounds=0, firstk=0, hs=0,
        )

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
            tot["firstk"]  += self._safe_int(my.get("firstkill"))
            tot["hs"]      += self._safe_int(my.get("hs"))

            sa = self._safe_int(jogos.get("score_a"_
