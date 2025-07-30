# ranking_handler.py
import json
from datetime import datetime
from collections import defaultdict
from botocore.exceptions import ClientError
import discord


def _is_mix_match(match_data: dict, group_gc_ids: set[str]) -> bool:
    """True se ambas as equipes tiverem ≥1 player do grupo."""
    jogadores = match_data.get("jogos", {}).get("players", {})
    a = jogadores.get("team_a", [])
    b = jogadores.get("team_b", [])
    a_grp = any(str(p.get("idplayer")) in group_gc_ids for p in a)
    b_grp = any(str(p.get("idplayer")) in group_gc_ids for p in b)
    return a_grp and b_grp


class RankingHandler:
    """
    Gera rankings mensais (ou all‑time) com opção de ignorar partidas de mix.
    """

    def __init__(self, s3, bucket, members_key):
        self.s3 = s3
        self.bucket = bucket
        self.members_key = members_key

    async def handle(self, ctx, args: str | None):
        """
        !ranking [YYYY‑MM | -all] [--exclude-mix | --no-mix | -nm]
        """
        # -------------------- parse --------------------
        month_arg = None
        exclude_mixes = False
        if args:
            for a in args.split():
                la = a.lower()
                if la in ("--exclude-mix", "--no-mix", "-nm"):
                    exclude_mixes = True
                elif la != "":
                    month_arg = a

        # ------------------ members --------------------
        try:
            body = self.s3.get_object(Bucket=self.bucket, Key=self.members_key)["Body"].read()
            members = json.loads(body.decode("utf-8"))
        except Exception:
            await ctx.send("Erro ao carregar members.json do S3.")
            return

        discord_to_gc = {did: str(info["gc"]) for did, info in members.items() if info.get("gc")}
        gc_to_nick = {str(info["gc"]): info.get("nickname", f"Unknown({info['gc']})")
                      for info in members.values() if info.get("gc")}
        group_gc_ids = set(gc_to_nick.keys())
        if not group_gc_ids:
            await ctx.send("Nenhum GC id configurado no members.json.")
            return

        # ------------------- período -------------------
        all_flag = (month_arg == "-all")
        if month_arg and not all_flag:
            try:
                datetime.strptime(month_arg, "%Y-%m")
                month_year = month_arg
            except ValueError:
                await ctx.send("Use YYYY‑MM ou -all. Ex.: `!ranking 2025-07 --no-mix`")
                return
        else:
            month_year = datetime.now().strftime("%Y-%m")

        # ------------------------------------------------
        # MODE 1 – rápido (sem flag): usa arquivos já agregados
        # ------------------------------------------------
        if not exclude_mixes:
            players = []
            prefix = ""  # nada além de month info
            for did, nick in ((did, gc_to_nick[str(info["gc"])])
                              for did, info in members.items() if info.get("gc")):
                gc = str(members[did]["gc"])
                stats_key = f"players/{gc}/stats-{month_year}.json"
                if all_flag:
                    # pegar todos arquivos stats‑AAAA‑MM
                    stats_files = self._list_prefix(f"players/{gc}/stats-")
                else:
                    stats_files = [stats_key]

                # agregação simples
                agg = self._aggregate_from_stats_files(stats_files)
                if not agg:
                    continue
                players.append({"nickname": nick, **agg})

        # ------------------------------------------------
        # MODE 2 – reconstruir lendo matches (flag ativa)
        # ------------------------------------------------
        else:
            players = self._aggregate_from_matches(
                month_year=month_year,
                all_flag=all_flag,
                exclude_mixes=True,
                group_gc_ids=group_gc_ids,
                gc_to_nick=gc_to_nick,
            )

        if not players:
            await ctx.send("Nenhum dado encontrado para este período.")
            return

        # -------------------- rankings ------------------
        def sort_metric(lst, key): return sorted(lst, key=lambda x: x[key], reverse=True)

        def txt(lst, key, label):
            return "\n".join(f"{i+1}. {p['nickname']} – {label}: {p[key]:.2f} ({p['matches']} part.)"
                             for i, p in enumerate(lst))

        embed = discord.Embed(
            title=f"Ranking {('All Time' if all_flag else month_year)}"
                  f"{' (sem mixes)' if exclude_mixes else ''}",
            description="Leaderboards do grupo",
            color=0x3498db
        )
        embed.add_field(name="KDR", value=f"```{txt(sort_metric(players,'kdr'),'kdr','KDR')}```", inline=False)
        embed.add_field(name="ADR", value=f"```{txt(sort_metric(players,'adr'),'adr','ADR')}```", inline=False)
        embed.add_field(name="Avg FK", value=f"```{txt(sort_metric(players,'avg_fk'),'avg_fk','Avg FK')}```", inline=False)
        embed.add_field(name="Win Rate", value=f"```{txt(sort_metric(players,'win_rate'),'win_rate','Win Rate')}```",
                        inline=False)
        await ctx.send(embed=embed)

    # -------------- helpers --------------
    def _list_prefix(self, prefix):
        try:
            res = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            return [obj["Key"] for obj in res.get("Contents", [])]
        except Exception:
            return []

    def _aggregate_from_stats_files(self, stats_files):
        if not stats_files:
            return None
        total = defaultdict(float)
        for key in stats_files:
            try:
                data = json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode("utf-8"))
            except ClientError:
                continue
            except Exception:
                continue
            total["matches"] += data.get("total_matches", 0)
            total["wins"] += data.get("total_wins", 0)
            total["kills"] += data.get("total_kills", 0)
            total["deaths"] += data.get("total_deaths", 0)
            total["first_kills"] += data.get("total_first_kills", 0)
            total["damage"] += data.get("ADR", 0) * data.get("total_matches", 0)
            total["rounds"] += data.get("average_rounds", 0) * data.get("total_matches", 0)  # opcional
        m = total["matches"]
        if m == 0:
            return None
        kdr = total["kills"] / total["deaths"] if total["deaths"] else total["kills"]
        adr = (total["damage"] / m) if m else 0
        avg_fk = total["first_kills"] / m
        win_rate = (total["wins"] / m * 100)
        return {"matches": int(m), "kdr": kdr, "adr": adr, "avg_fk": avg_fk, "win_rate": win_rate}

    def _aggregate_from_matches(self, month_year, all_flag, exclude_mixes,
                                group_gc_ids, gc_to_nick):
        players = defaultdict(lambda: defaultdict(float))
        listed = self._list_prefix("matches/")
        from datetime import datetime
        for key in listed:
            try:
                match = json.loads(self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode("utf-8"))
            except Exception:
                continue
            # filtro de data
            date_str = match.get("data")
            if not all_flag:
                try:
                    d = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                    if d.strftime("%Y-%m") != month_year:
                        continue
                except Exception:
                    continue
            # excluir mix?
            if exclude_mixes and _is_mix_match(match, group_gc_ids):
                continue

            jogos = match.get("jogos", {})
            players_data = jogos.get("players", {})
            try:
                sa = int(jogos.get("score_a", 0))
                sb = int(jogos.get("score_b", 0))
            except Exception:
                sa = sb = 0
            winning_team = "team_a" if sa > sb else "team_b" if sb > sa else None

            for team_name in ("team_a", "team_b"):
                for p in players_data.get(team_name, []):
                    gc = str(p.get("idplayer"))
                    if gc not in group_gc_ids:
                        continue
                    st = players[gc]
                    st["matches"] += 1
                    st["kills"] += int(p.get("nb_kill", 0))
                    st["deaths"] += int(p.get("death", 0))
                    st["damage"] += int(p.get("damage", 0))
                    st["rounds"] += int(p.get("rounds_played", 0))
                    st["first_kills"] += int(p.get("firstkill", 0))
                    if winning_team == team_name:
                        st["wins"] += 1

        # finalizar métricas
        out = []
        for gc, st in players.items():
            m = st["matches"]
            if m == 0:
                continue
            kdr = st["kills"] / st["deaths"] if st["deaths"] else st["kills"]
            adr = st["damage"] / st["rounds"] if st["rounds"] else 0
            avg_fk = st["first_kills"] / m
            win_rate = st["wins"] / m * 100
            out.append({"nickname": gc_to_nick.get(gc, f"Unknown({gc})"),
                        "matches": int(m), "kdr": kdr, "adr": adr,
                        "avg_fk": avg_fk, "win_rate": win_rate})
        return out
