import json
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
from botocore.exceptions import ClientError
import discord

class RankingMixHandler:
    def __init__(self, s3_client, bucket_name, object_key, max_workers=10):
        self.s3 = s3_client
        self.bucket = bucket_name
        self.object_key = object_key
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def handle(self, ctx: discord.ext.commands.Context, args: str = None):
        # Parse flags
        period = None
        all_flag = False
        last_n = 10
        tokens = args.split() if args else []
        clean = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.lower() in ("-last", "-l") and i + 1 < len(tokens):
                try:
                    last_n = int(tokens[i+1])
                    i += 2
                    continue
                except ValueError:
                    pass
            clean.append(tok)
            i += 1

        if clean:
            if clean[0] == "-all":
                all_flag = True
            else:
                try:
                    datetime.strptime(clean[0], "%Y-%m")
                    period = clean[0]
                except ValueError:
                    await ctx.send("Invalid period; use YYYY-MM or '-all'.")
                    return
        month_year = None if all_flag else (period or datetime.now().strftime("%Y-%m"))

        # Load members.json
        try:
            resp = self.s3.get_object(Bucket=self.bucket, Key=self.object_key)
            members = json.loads(resp["Body"].read().decode())
        except Exception:
            await ctx.send("Error loading members data from S3.")
            return
        discord_to_gc = {did: str(info.get("gc")) for did, info in members.items() if info.get("gc")}
        gc_to_nick = {str(info.get("gc")): info.get("nickname", f"Unknown({info.get('gc')})") for info in members.values() if info.get("gc")}
        if not discord_to_gc:
            await ctx.send("No group GC ids found in members data.")
            return

        # List match keys
        try:
            list_resp = self.s3.list_objects_v2(Bucket=self.bucket, Prefix="matches/")
            keys = [o["Key"] for o in list_resp.get("Contents", [])]
        except Exception:
            await ctx.send("Error listing match objects from S3.")
            return

        # Parallel fetch
        loop = asyncio.get_event_loop()
        async def fetch(key):
            try:
                data = await loop.run_in_executor(
                    self.executor,
                    lambda: self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read().decode()
                )
                return key, json.loads(data)
            except Exception:
                return key, None
        fetched = await asyncio.gather(*(fetch(k) for k in keys))

        # Collect records
        records = {}
        seen = set()
        for key, match in fetched:
            if not match:
                continue
            date_str = match.get("data")
            mdate = None
            if date_str:
                try: mdate = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                except: pass
            if month_year and (not mdate or mdate.strftime("%Y-%m") != month_year):
                continue
            mid = match.get("id") or match.get("match_id") or key.split("/")[-1]
            if mid in seen:
                continue
            seen.add(mid)
            jogos = match.get("jogos", {})
            players = jogos.get("players", {})
            try:
                score_a = int(jogos.get("score_a",0)); score_b = int(jogos.get("score_b",0))
            except:
                score_a = score_b = 0
            winner = "team_a" if score_a>score_b else "team_b" if score_b>score_a else None
            def rec(p, team):
                gc = str(p.get("idplayer"))
                if gc not in records: records[gc] = []
                records[gc].append({
                    "date": mdate or datetime.min,
                    "kills": int(p.get("nb_kill",0)),
                    "deaths": int(p.get("death",0)),
                    "damage": int(p.get("damage",0)),
                    "rounds": int(p.get("rounds_played",0)),
                    "first_kills": int(p.get("firstkill",0)),
                    "win": 1 if winner==team else 0
                })
            for p in players.get("team_a", []):
                if str(p.get("idplayer")) in discord_to_gc.values(): rec(p, "team_a")
            for p in players.get("team_b", []):
                if str(p.get("idplayer")) in discord_to_gc.values(): rec(p, "team_b")

        # Aggregate last_n
        stats_list = []
        for gc, recs in records.items():
            recs = sorted(recs, key=lambda r: r["date"])[-last_n:]
            if not recs: continue
            tot = len(recs)
            S = {k: sum(r[k] for r in recs) for k in ("kills","deaths","damage","rounds","first_kills","win")}
            kdr = S["kills"]/S["deaths"] if S["deaths"] else S["kills"]
            adr = S["damage"]/S["rounds"] if S["rounds"] else 0
            avg_fk = S["first_kills"]/tot
            wr = S["win"]/tot*100
            stats_list.append({"nick": gc_to_nick.get(gc), "kdr": kdr, "adr": adr, "fk": avg_fk, "wr": wr, "m": tot})

        if not stats_list:
            await ctx.send("No mix matches found.")
            return
        def build(lst, key, lbl):
            return "\n".join(f"{i+1}. {p['nick']} - {lbl}: {p[key]:.2f} ({p['m']} matches)" for i,p in enumerate(lst))
        sorted_stats = {"KDR": sorted(stats_list, key=lambda x: x["kdr"], reverse=True),
                        "ADR": sorted(stats_list, key=lambda x: x["adr"], reverse=True),
                        "Avg FK": sorted(stats_list, key=lambda x: x["fk"], reverse=True),
                        "Win Rate": sorted(stats_list, key=lambda x: x["wr"], reverse=True)}
        title = f"Mix Ranking {'All Time' if all_flag else month_year} (Last {last_n})"
        embed = discord.Embed(title=title, description=f"Last {last_n} matches stats", color=0x9b59b6)
        for lbl, lst in sorted_stats.items():
            embed.add_field(name=lbl, value=f"```{build(lst, lbl.lower().replace(' ','_'), lbl)}```", inline=False)
        await ctx.send(embed=embed)