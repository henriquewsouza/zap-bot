# ranking_creator_handler.py
import re, json, asyncio
from collections import defaultdict
from datetime import datetime
import discord
from botocore.exceptions import ClientError


class RankingCreatorHandler:
    """
    Gera ranking de win‑rate dos criadores de lobby (admins da partida).

    Uso no Discord:
      !ranking_creators                    -> mês atual
      !ranking_creators 2025-03            -> março/2025
      !ranking_creators -all               -> all‑time
    """

    MATCH_PREFIX = "matches/"           # pasta no S3 com as partidas
    MIN_LOBBIES = 5                     # amostragem mínima por admin

    def __init__(self, s3_client, bucket_name: str, members_key: str):
        self.s3 = s3_client
        self.bucket = bucket_name
        self.members_key = members_key          # normalmente "members.json"

    # ---------- API pública ----------
    async def handle(self, ctx, args: str | None = None):
        period = (args or "").strip() if args else ""
        all_flag = (period == "-all")
        if not all_flag and period:
            try:
                datetime.strptime(period, "%Y-%m")
            except ValueError:
                await ctx.send("Use `YYYY-MM` ou `-all`.")
                return
        if not period:
            period = datetime.now().strftime("%Y-%m")

        members = self._load_members()
        gc_ids_group = {str(m["gc"]) for m in members.values() if m.get("gc")}
        gc2nick = {str(m["gc"]): m.get("nickname", f"GC {m['gc']}") for m in members.values() if m.get("gc")}

        stats = await asyncio.to_thread(
            self._collect_stats, gc_ids_group, period, all_flag
        )
        if not stats:
            await ctx.send("Nenhum criador de lobby do grupo encontrado no período.")
            return

        ranking = [
            (gc2nick[gc], data["wins"], data["matches"],
             data["wins"] / data["matches"] * 100)
            for gc, data in stats.items() if data["matches"] >= self.MIN_LOBBIES
        ]
        ranking.sort(key=lambda x: x[3], reverse=True)

        if not ranking:
            await ctx.send(f"Ninguém atingiu {self.MIN_LOBBIES} lobbys no período.")
            return

        text = "\n".join(
            f"{i+1}. {nick} – WR {wr:.2f}% ({w}/{m})"
            for i, (nick, w, m, wr) in enumerate(ranking)
        )

        embed = discord.Embed(
            title=f"Ranking – Criadores de Lobby ({'All Time' if all_flag else period})",
            description="Win‑rate considerando *todas* as lobbys em que o jogador foi admin.",
            color=0xe67e22
        )
        embed.add_field(name="🏆 Win‑Rate", value=f"```{text}```", inline=False)
        await ctx.send(embed=embed)

    # ---------- coleta ----------
    def _collect_stats(self, group_ids: set[str], period: str, all_flag: bool):
        """
        Varrre todos os JSON em matches/ e devolve:
            { gc_id: {wins: int, matches: int}, ... }
        """
        stats = defaultdict(lambda: {"wins": 0, "matches": 0})
        objects = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=self.MATCH_PREFIX).get("Contents", [])

        for obj in objects:
            key = obj["Key"]
            try:
                body = self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode("utf-8")
                match = json.loads(body)
            except Exception:
                continue

            # filtro de período
            if not all_flag:
                date_str = match.get("data")
                if not date_str:
                    continue
                try:
                    if datetime.strptime(date_str, "%d/%m/%Y %H:%M").strftime("%Y-%m") != period:
                        continue
                except Exception:
                    continue

            admin_a = self._extract_admin_id(match.get("admin_avatar_a"))
            admin_b = self._extract_admin_id(match.get("admin_avatar_b"))

            # vencedor
            jogos = match.get("jogos", {})
            try:
                score_a = int(jogos.get("score_a", 0))
                score_b = int(jogos.get("score_b", 0))
            except Exception:
                score_a = score_b = 0
            winner = "a" if score_a > score_b else "b" if score_b > score_a else None

            def add_result(admin_gc: str | None, side: str):
                if admin_gc in group_ids:
                    stats[admin_gc]["matches"] += 1
                    if winner == side:
                        stats[admin_gc]["wins"] += 1

            add_result(admin_a, "a")
            add_result(admin_b, "b")

        return stats

    # ---------- utilidades ----------
    def _load_members(self) -> dict:
        try:
            cont = self.s3.get_object(Bucket=self.bucket, Key=self.members_key)["Body"].read().decode("utf-8")
            return json.loads(cont)
        except ClientError:
            return {}

    @staticmethod
    def _extract_admin_id(url: str | None) -> str | None:
        """
        Ex.: https://static.gamersclub.com.br/players/avatar/1323034/1323034_medium.jpg
        -> "1323034"
        """
        if not url:
            return None
        m = re.search(r"/avatar/(\d+)/", url)
        return m.group(1) if m else None
