# ranking_creator_handler.py
import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, Optional, Set

import discord
from botocore.exceptions import ClientError


class RankingCreatorHandler:
    """
    Calcula o win‑rate dos criadores de lobby (admins de partida).

    Comandos esperados no Discord:
      !ranking_creators              -> mês atual
      !ranking_creators YYYY-MM      -> mês específico (ex.: 2025-03)
      !ranking_creators -all         -> all‑time
    """

    MATCH_PREFIX: str = "matches/"   # pasta no S3 onde ficam os JSON de partidas
    MIN_LOBBIES: int = 10             # qtd. mínima de lobbys para entrar no ranking

    # --------------------------------------------------------------------- #
    #  Construtor                                                           #
    # --------------------------------------------------------------------- #
    def __init__(self, s3_client, bucket_name: str, members_key: str):
        self.s3 = s3_client
        self.bucket = bucket_name
        self.members_key = members_key  # geralmente "members.json"

    # --------------------------------------------------------------------- #
    #  Entrada principal chamada pelo bot                                   #
    # --------------------------------------------------------------------- #
    async def handle(self, ctx, args: Optional[str] = None):
        period = (args or "").strip() if args else ""
        all_flag = period == "-all"

        # Validação do período
        if not all_flag and period:
            try:
                datetime.strptime(period, "%Y-%m")
            except ValueError:
                await ctx.send("Use `YYYY-MM` ou `-all`.")
                return
        if not period:
            period = datetime.now().strftime("%Y-%m")

        members = self._load_members()
        gc_ids_group: Set[str] = {
            str(m["gc"]) for m in members.values() if m.get("gc")
        }
        gc2nick: Dict[str, str] = {
            str(m["gc"]): m.get("nickname", f"GC {m['gc']}")
            for m in members.values()
            if m.get("gc")
        }

        # Coleta é bloqueante → executa em thread
        stats = await asyncio.to_thread(
            self._collect_stats, gc_ids_group, period, all_flag
        )
        if not stats:
            await ctx.send("Nenhum criador de lobby do grupo encontrado no período.")
            return

        # Constrói ranking
        ranking = [
            (
                gc2nick.get(gc, f"GC {gc}"),
                data["wins"],
                data["matches"],
                data["wins"] / data["matches"] * 100,
            )
            for gc, data in stats.items()
            if data["matches"] >= self.MIN_LOBBIES
        ]
        ranking.sort(key=lambda x: x[3], reverse=True)

        if not ranking:
            await ctx.send(
                f"Ninguém atingiu {self.MIN_LOBBIES} lobbys no período selecionado."
            )
            return

        text = "\n".join(
            f"{i+1}. {nick} – WR {wr:.2f}% ({w}/{m})"
            for i, (nick, w, m, wr) in enumerate(ranking)
        )

        embed = discord.Embed(
            title=f"Ranking – Criadores de Lobby ({'All Time' if all_flag else period})",
            description="Win‑rate considerando apenas lobbys em que o jogador foi admin.",
            color=0xE67E22,
        )
        embed.add_field(name="🏆 Win‑Rate", value=f"```{text}```", inline=False)
        await ctx.send(embed=embed)

    # --------------------------------------------------------------------- #
    #  Coleta de estatísticas                                               #
    # --------------------------------------------------------------------- #
    def _collect_stats(
        self, group_ids: Set[str], period: str, all_flag: bool
    ) -> Dict[str, Dict[str, int]]:
        """
        Varre todos os JSON em matches/ e retorna:
            { gc_id: {'wins': int, 'matches': int}, ... }
        """
        stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"wins": 0, "matches": 0}
        )
        objects = (
            self.s3.list_objects_v2(Bucket=self.bucket, Prefix=self.MATCH_PREFIX).get(
                "Contents", []
            )
        )

        for obj in objects:
            key = obj["Key"]
            try:
                body = (
                    self.s3.get_object(Bucket=self.bucket, Key=key)["Body"]
                    .read()
                    .decode("utf-8")
                )
                match = json.loads(body)
            except Exception:
                continue

            # Filtra por período, se não for all‑time
            if not all_flag:
                date_str = match.get("data")  # "dd/mm/YYYY HH:MM"
                if not date_str:
                    continue
                try:
                    if (
                        datetime.strptime(date_str, "%d/%m/%Y %H:%M").strftime("%Y-%m")
                        != period
                    ):
                        continue
                except Exception:
                    continue

            admin_a = self._extract_admin_id(match.get("admin_avatar_a"))
            admin_b = self._extract_admin_id(match.get("admin_avatar_b"))

            jogos = match.get("jogos", {})
            try:
                score_a = int(jogos.get("score_a", 0))
                score_b = int(jogos.get("score_b", 0))
            except Exception:
                score_a = score_b = 0
            winner = "a" if score_a > score_b else "b" if score_b > score_a else None

            def add_result(admin_gc: Optional[str], side: str):
                if admin_gc in group_ids:
                    stats[admin_gc]["matches"] += 1
                    if winner == side:
                        stats[admin_gc]["wins"] += 1

            add_result(admin_a, "a")
            add_result(admin_b, "b")

        return stats

    # --------------------------------------------------------------------- #
    #  Utilidades                                                           #
    # --------------------------------------------------------------------- #
    def _load_members(self) -> Dict:
        try:
            content = (
                self.s3.get_object(Bucket=self.bucket, Key=self.members_key)["Body"]
                .read()
                .decode("utf-8")
            )
            return json.loads(content)
        except ClientError:
            return {}

    @staticmethod
    def _extract_admin_id(url: Optional[str]) -> Optional[str]:
        """
        Extrai o GC ID do admin a partir do avatar:
        https://static.gamersclub.com.br/players/avatar/1323034/1323034_medium.jpg
        -> "1323034"
        """
        if not url:
            return None
        m = re.search(r"/avatar/(\d+)/", url)
        return m.group(1) if m else None
