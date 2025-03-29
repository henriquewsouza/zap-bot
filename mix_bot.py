import os
import getpass  # Securely prompt for the token without echoing it
import discord
from discord.ext import commands
import itertools
import json
import asyncio
import random
import boto3
from datetime import datetime
from botocore.exceptions import ClientError

# ---------------------------
# Configuration
# ---------------------------

# Discord Bot Configuration
BOT_ADMINS = [291617683416285194, 701661704844738580]

# Lightsail Bucket (S3‑compatible) Configuration
BUCKET_NAME = "bucket-6sk08y"       # Your Lightsail bucket name
OBJECT_KEY = "members.json"         # The object key for persistent data
# Option B: Using the standard S3 endpoint. If needed, you can try using the bucket domain as the endpoint.
ENDPOINT_URL = "https://s3.us-east-1.amazonaws.com"

# Create an S3 client using the custom endpoint
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)

# ---------------------------
# Persistence Functions
# ---------------------------

def load_user_levels():
    """
    Load user levels from the Lightsail bucket.
    If the object doesn't exist, return an empty dictionary.
    """
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        contents = response["Body"].read().decode("utf-8")
        user_data = json.loads(contents)
        return {int(user_id): info for user_id, info in user_data.items()}
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            # Object not found; return empty data.
            return {}
        else:
            raise

def save_user_levels(user_levels):
    """
    Save user levels to the Lightsail bucket.
    """
    data = json.dumps({str(uid): info for uid, info in user_levels.items()}, indent=4)
    s3.put_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY, Body=data.encode("utf-8"))

# Global in-memory user_levels loaded from the bucket

# ---------------------------
# Discord Bot Setup
# ---------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
user_levels = load_user_levels()

# Global flag to prevent concurrent mixes.
mix_in_progress = False

# ---------------------------
# Team Building Helpers
# ---------------------------

def build_team_message(team1, team2):
    """
    Constructs a message displaying both teams, sorted by level (highest first),
    with total team skills and the difference.
    """
    sorted_team1 = sorted(team1, key=lambda m: user_levels[m.id]["level"], reverse=True)
    sorted_team2 = sorted(team2, key=lambda m: user_levels[m.id]["level"], reverse=True)
    
    total_team1 = sum(user_levels[m.id]["level"] for m in sorted_team1)
    total_team2 = sum(user_levels[m.id]["level"] for m in sorted_team2)
    
    team1_text = "\n".join(f"{m.mention} (Level: {user_levels[m.id]['level']})" for m in sorted_team1)
    team2_text = "\n".join(f"{m.mention} (Level: {user_levels[m.id]['level']})" for m in sorted_team2)
    
    message = (
        f"**Team 1:**\n{team1_text}\n**Total Skill:** {total_team1}\n\n"
        f"**Team 2:**\n{team2_text}\n**Total Skill:** {total_team2}\n\n"
        f"**Difference:** {abs(total_team1 - total_team2)}\n\n"
        f"**Lembre-se: Se vc sacanear o Zap é melhor esperar que ele não descubra seu IP**"
    )
    return message

def generate_valid_partitions(members):
    """
    Generate all valid team partitions from the list of members.
    For even numbers, teams are equal; for odd, team1 gets floor(n/2) members.
    Returns a list of tuples: (difference, team1, team2).
    """
    partitions = []
    n = len(members)
    team1_size = n // 2  # If odd, team2 will have one extra member.
    for team1 in itertools.combinations(members, team1_size):
        team2 = [member for member in members if member not in team1]
        total_team1 = sum(user_levels[m.id]["level"] for m in team1)
        total_team2 = sum(user_levels[m.id]["level"] for m in team2)
        diff = abs(total_team1 - total_team2)
        partitions.append((diff, team1, team2))
    return partitions

async def send_mix_result(channel, team1, team2):
    """
    Sends the generated team partition result to the specified channel.
    """
    message = build_team_message(team1, team2)
    await channel.send("**Teams Generated:**\n" + message)

# ---------------------------
# Parsing Helpers for Mix Command
# ---------------------------

async def parse_mix_args(ctx):
    """
    Parse command arguments from ctx.message.content.
    Expected format:
      !mix [<number>] [--exclude or -e] <member mentions> [--extra or -x] <member mentions>
    Returns a tuple: (combination_count, exclusions, extras)
    """
    args = ctx.message.content.split()[1:]  # skip the command name
    combination_count = 1  # default value
    if args and args[0].isdigit():
        combination_count = int(args[0])
        args = args[1:]
    
    mode = None
    exclusions = []
    extras = []
    converter = commands.MemberConverter()
    for arg in args:
        if arg.lower() in ("-e", "--exclude"):
            mode = "exclude"
        elif arg.lower() in ("-x", "--extra"):
            mode = "extra"
        else:
            try:
                member = await converter.convert(ctx, arg)
            except commands.BadArgument:
                continue
            if mode is None:
                mode = "extra"
            if mode == "exclude":
                exclusions.append(member)
            elif mode == "extra":
                extras.append(member)
    return combination_count, exclusions, extras

def get_mix_members(ctx, exclusions, extras):
    """
    Build the final list of members for the mix from:
      - Non‑bot members in the voice channel (if any), minus exclusions.
      - Extra members specified.
    """
    members = []
    if ctx.author.voice is not None:
        voice_members = [member for member in ctx.author.voice.channel.members if not member.bot]
        members.extend(voice_members)
    exclusions_ids = {member.id for member in exclusions}
    members = [m for m in members if m.id not in exclusions_ids]
    for member in extras:
        if all(member.id != m.id for m in members):
            members.append(member)
    return members

# ---------------------------
# Bot Commands
# ---------------------------

@bot.command(name="mix")
async def mix_teams(ctx):
    """
    !mix [<number>] [--exclude @User ...] [--extra @User ...]
    Generates one or more balanced team partitions from non‑bot members.
    If any member does not have a level set, their name is reported.
    """
    global mix_in_progress
    if mix_in_progress:
        await ctx.send("A team mix is already in progress. Please wait until it is finished.")
        return

    mix_in_progress = True
    try:
        channel = ctx.channel
        combination_count, exclusions, extras = await parse_mix_args(ctx)
        members = get_mix_members(ctx, exclusions, extras)
        if len(members) < 2:
            await channel.send("There are not enough members to form teams.")
            return
        
        missing_members = [m for m in members if m.id not in user_levels]
        if missing_members:
            missing_names = ", ".join(m.display_name for m in missing_members)
            await channel.send("The following members do not have a level set: " + missing_names)
            return

        partitions = generate_valid_partitions(members)
        if not partitions:
            await channel.send("No valid team partitions available with the current constraints.")
            return

        partitions.sort(key=lambda x: x[0])
        combination_count = min(combination_count, len(partitions))
        messages = []
        for i in range(combination_count):
            diff, team1, team2 = partitions[i]
            message = f"**Combination #{i+1}:**\n" + build_team_message(team1, team2)
            messages.append(message)
        
        for message in messages:
            await channel.send(message)
    finally:
        mix_in_progress = False

@bot.command(name="arere")
async def arere(ctx):
    """
    !arere
    Randomly splits all non‑bot members from your current voice channel into two teams.
    """
    if ctx.author.voice is None:
        await ctx.send("You need to be in a voice channel to use this command.")
        return

    members = [member for member in ctx.author.voice.channel.members if not member.bot]
    if len(members) < 2:
        await ctx.send("Not enough members in the voice channel to mix teams.")
        return

    random.shuffle(members)
    mid = len(members) // 2
    team1 = members[:mid]
    team2 = members[mid:]
    
    team1_text = "\n".join(member.mention for member in team1)
    team2_text = "\n".join(member.mention for member in team2)
    message = (
        "**Random Team Assignment:**\n\n"
        f"**Team 1:**\n{team1_text}\n\n"
        f"**Team 2:**\n{team2_text}"
    )
    
    await ctx.send(message)

@bot.command(name="clear")
@commands.check(lambda ctx: ctx.author.id in BOT_ADMINS)
@commands.has_permissions(manage_messages=True)
async def clear(ctx):
    """
    !clear
    Clears all (non-pinned) messages from the current channel.
    (Requires Manage Messages permission; Bot Admins only.)
    """
    channel = ctx.channel
    deleted = await channel.purge(limit=None)
    confirmation = await channel.send(f"Cleared {len(deleted)} messages from this channel.")
    await asyncio.sleep(5)
    await confirmation.delete()

@bot.command(name="setlevel")
@commands.check(lambda ctx: ctx.author.id in BOT_ADMINS)
async def set_level(ctx, member: discord.Member, level: int):
    """
    !setlevel @User <level>
    Permanently updates a member's level and saves the change to the Lightsail bucket.
    (Bot Admins only.)
    """
    global user_levels
    user_levels[member.id] = {
        "level": level,
        "nickname": member.display_name
    }
    save_user_levels(user_levels)
    await ctx.send(f"Updated {member.mention}'s level to {level}.")

@bot.command(name="addtemp")
@commands.check(lambda ctx: ctx.author.id in BOT_ADMINS)
async def add_temp(ctx, member: discord.Member, level: int):
    """
    !addtemp @User <level>
    Temporarily adds a member with a given level (in-memory only).
    (Bot Admins only.)
    """
    global user_levels
    if member.id in user_levels:
        await ctx.send(f"{member.mention} is already in the user list. Use !setlevel to update their level.")
        return
    user_levels[member.id] = {
        "level": level,
        "nickname": member.display_name
    }
    await ctx.send(f"Temporarily added {member.mention} with level {level}.")

@bot.command(name="players")
async def players(ctx):
    """
    !players
    Displays the list of all users in the system along with their levels and nicknames.
    """
    if not user_levels:
        await ctx.send("No players are currently in the list.")
        return

    sorted_players = sorted(user_levels.items(), key=lambda item: item[1]["level"], reverse=True)
    msg_lines = ["**Current Players:**"]
    for user_id, info in sorted_players:
        msg_lines.append(f"**{info.get('nickname', 'Unknown')}** - Level: {info.get('level', 'N/A')}")
    help_message = "\n".join(msg_lines)
    if len(help_message) > 1900:
        for i in range(0, len(help_message), 1900):
            await ctx.send(help_message[i:i+1900])
    else:
        await ctx.send(help_message)

@bot.command(name="help")
async def help_command(ctx):
    """
    !help
    Displays the list of available bot commands.
    """
    help_text = (
        "**Bot Commands:**\n"
        "**!mix [<number>] [--exclude @User ...] [--extra @User ...]**\n"
        "   - Generates one or more balanced team partitions from non‑bot members.\n"
        "     (If any member does not have a level set, their name will be reported.)\n"
        "**!arere**\n"
        "   - Randomly splits voice channel members into two teams.\n"
        "**!clear**\n"
        "   - Clears all (non-pinned) messages from the current channel. (Requires Manage Messages; Bot Admins only.)\n"
        "**!setlevel @User <level>**\n"
        "   - Permanently updates a member's level and saves the change to the Lightsail bucket. (Bot Admins only.)\n"
        "**!addtemp @User <level>**\n"
        "   - Temporarily adds a member with a given level (in-memory only). (Bot Admins only.)\n"
        "**!players**\n"
        "   - Displays the current list of players along with their levels and nicknames.\n"
        "**!botadmins**\n"
        "   - Displays the current list of Bot Admins along with their nicknames and levels."
    )
    await ctx.send(help_text)

@bot.command(name="botadmins")
async def botadmins(ctx):
    """
    !botadmins
    Displays the list of bot admins along with their nicknames and levels.
    """
    msg_lines = ["**Bot Admins:**"]
    for admin_id in BOT_ADMINS:
        info = user_levels.get(admin_id)
        if info:
            msg_lines.append(f"<@{admin_id}> - Nickname: **{info.get('nickname', 'Unknown')}**, Level: **{info.get('level', 'N/A')}**")
        else:
            msg_lines.append(f"<@{admin_id}> - No info available.")
    await ctx.send("\n".join(msg_lines))

@bot.command(name="stats")
async def stats(ctx, member: discord.Member):
    """
    !stats @Player
    Retrieves aggregated stats for the mentioned player for the current month.
    Overall stats include total matches, wins, losses, win rate, kills, deaths,
    overall KDR, overall ADR, total first kills, average first kills per match, and HS%.
    Per-map stats include the number of matches, win rate, KDR, and ADR for each map.
    """
    # Load the members.json file from the root folder.
    try:
        with open("members.json", "r") as f:
            members_data = json.load(f)
    except Exception as e:
        await ctx.send("Error loading members data.")
        return

    discord_id_str = str(member.id)
    if discord_id_str not in members_data:
        await ctx.send(f"{member.display_name} is not in the members list.")
        return

    # Retrieve the GC id for the member.
    gc_id = members_data[discord_id_str].get("gc")
    if not gc_id:
        await ctx.send(f"{member.display_name} does not have a valid GC id set.")
        return

    from datetime import datetime
    month_year = datetime.now().strftime("%Y-%m")
    # Construct the stats file path (e.g., players/829311/stats-2025-03.json)
    stats_path = os.path.join("players", str(gc_id), f"stats-{month_year}.json")
    if not os.path.exists(stats_path):
        await ctx.send(f"Stats for {member.display_name} for {month_year} are not available.")
        return

    try:
        with open(stats_path, "r") as f:
            stats_data = json.load(f)
    except Exception as e:
        await ctx.send("Error loading the stats file.")
        return

    # Build an embed message to display the overall stats.
    embed = discord.Embed(
        title=f"Stats for {member.display_name} - {month_year}",
        color=0x00ff00
    )
    embed.add_field(name="Total Matches", value=stats_data.get("total_matches", 0), inline=True)
    embed.add_field(name="Wins", value=stats_data.get("total_wins", 0), inline=True)
    embed.add_field(name="Losses", value=stats_data.get("total_losses", 0), inline=True)
    embed.add_field(name="Overall Win Rate", value=f"{stats_data.get('overall_win_rate', 0):.2f}%", inline=True)
    embed.add_field(name="Total Kills", value=stats_data.get("total_kills", 0), inline=True)
    embed.add_field(name="Total Deaths", value=stats_data.get("total_deaths", 0), inline=True)
    embed.add_field(name="KDR", value=f"{stats_data.get('KDR', 0):.2f}", inline=True)
    embed.add_field(name="ADR", value=f"{stats_data.get('ADR', 0):.2f}", inline=True)
    embed.add_field(name="Total First Kills", value=stats_data.get("total_first_kills", 0), inline=True)
    embed.add_field(name="Avg First Kills/Match", value=f"{stats_data.get('average_first_kills_per_match', 0):.2f}", inline=True)
    embed.add_field(name="HS%", value=f"{stats_data.get('HS_percent', 0):.2f}%", inline=True)

    # Build per-map stats.
    # It expects stats_data["per_map"] to be a dict where each key is a map name and its value is another dict with:
    # "matches", "wins", "kills", "deaths", "damage", and "rounds".
    per_map_data = stats_data.get("per_map", {})
    per_map_str = ""
    if per_map_data:
        for map_name, mstats in per_map_data.items():
            matches = mstats.get("matches", 0)
            wins = mstats.get("wins", 0)
            win_rate = (wins / matches * 100) if matches > 0 else 0

            kills = mstats.get("kills", 0)
            deaths = mstats.get("deaths", 0)
            damage = mstats.get("damage", 0)
            rounds = mstats.get("rounds", 0)

            # Calculate per-map KDR and ADR
            kdr = kills / deaths if deaths > 0 else kills
            adr = damage / rounds if rounds > 0 else 0

            per_map_str += (
                f"**{map_name}**: Matches: {matches}, Win Rate: {win_rate:.2f}%, "
                f"KDR: {kdr:.2f}, ADR: {adr:.2f}\n"
            )
    else:
        per_map_str = "No per-map stats available."

    embed.add_field(name="Per Map Stats", value=per_map_str, inline=False)
    await ctx.send(embed=embed)

@bot.command(name="update")
async def update(ctx, member: discord.Member):
    """
    !update @Member
    Updates the stats for the mentioned member for the current month.
    This command will:
      1. Retrieve the member's match history.
      2. Download full match stats for each match.
      3. Aggregate the match stats.
    The data is saved under /players/{GC id}/.
    """
    import os, json, asyncio
    from datetime import datetime
    from match_history import get_match_history
    from load_match_stats import load_match_stats
    from aggregate_player_stats import aggregate_stats

    # Load members.json from the root folder.
    members_file = "members.json"
    if not os.path.exists(members_file):
        await ctx.send("members.json not found in root folder.")
        return

    with open(members_file, "r") as f:
        members_data = json.load(f)

    discord_id_str = str(member.id)
    if discord_id_str not in members_data:
        await ctx.send(f"{member.display_name} is not in the members list.")
        return

    gc_id = members_data[discord_id_str].get("gc")
    if not gc_id:
        await ctx.send(f"{member.display_name} does not have a GC id set.")
        return

    # Get current month and year (YYYY-MM)
    month_year = datetime.now().strftime("%Y-%m")
    await ctx.send(f"Updating stats for {member.mention} (GC: {gc_id}) for {month_year} ...")

    # Define a blocking function that processes the member.
    def process_member(gc_id, month_year):
        history_file = get_match_history(gc_id, month_year)
        load_match_stats(history_file)
        aggregate_stats(gc_id, month_year)

    # Run the blocking processing in a separate thread.
    await asyncio.to_thread(process_member, gc_id, month_year)

    await ctx.send(f"Update complete for {member.mention}.")



@bot.command(name="ranking")
async def ranking(ctx):
    """
    !ranking
    Displays a ranking of members (from members.json) for the current month,
    based on overall KDR, ADR, average first kills per match, and overall win rate.
    Each ranking shows the member's nickname, metric value, and total matches played.
    """
    import os, json
    from datetime import datetime

    # Load members.json from the root folder
    try:
        with open("members.json", "r") as f:
            members_data = json.load(f)
    except Exception as e:
        await ctx.send("Error loading members data.")
        return

    # Get current month and year (YYYY-MM)
    month_year = datetime.now().strftime("%Y-%m")
    
    # List to store stats for each member with an aggregated file
    stats_list = []
    
    for discord_id, info in members_data.items():
        gc_id = info.get("gc")
        if not gc_id:
            continue
        # Construct path to aggregated stats file
        stats_path = os.path.join("players", str(gc_id), f"stats-{month_year}.json")
        if not os.path.exists(stats_path):
            continue
        try:
            with open(stats_path, "r") as f:
                stats = json.load(f)
        except Exception as e:
            continue
        
        # Extract overall metrics
        kdr = stats.get("KDR", 0)
        adr = stats.get("ADR", 0)
        avg_first = stats.get("average_first_kills_per_match", 0)
        win_rate = stats.get("overall_win_rate", 0)
        total_matches = stats.get("total_matches", 0)
        nickname = info.get("nickname", "Unknown")
        
        stats_list.append({
            "discord_id": discord_id,
            "nickname": nickname,
            "kdr": kdr,
            "adr": adr,
            "avg_first": avg_first,
            "win_rate": win_rate,
            "matches": total_matches
        })
    
    if not stats_list:
        await ctx.send("No aggregated stats found for this month.")
        return

    # For each metric, sort the list in descending order (higher is better)
    kdr_sorted = sorted(stats_list, key=lambda x: x["kdr"], reverse=True)
    adr_sorted = sorted(stats_list, key=lambda x: x["adr"], reverse=True)
    first_sorted = sorted(stats_list, key=lambda x: x["avg_first"], reverse=True)
    win_rate_sorted = sorted(stats_list, key=lambda x: x["win_rate"], reverse=True)

    # Helper function to build a ranking string
    def build_ranking_str(sorted_list, metric_key, metric_name):
        lines = []
        for idx, stat in enumerate(sorted_list, start=1):
            value = stat[metric_key]
            lines.append(f"{idx}. {stat['nickname']} - {metric_name}: {value:.2f} ({stat['matches']} matches)")
        return "\n".join(lines)

    ranking_kdr = build_ranking_str(kdr_sorted, "kdr", "KDR")
    ranking_adr = build_ranking_str(adr_sorted, "adr", "ADR")
    ranking_first = build_ranking_str(first_sorted, "avg_first", "Avg First Kills")
    ranking_win = build_ranking_str(win_rate_sorted, "win_rate", "Win Rate")

    # Create an embed with each ranking as a separate field.
    embed = discord.Embed(
        title=f"Member Rankings for {month_year}",
        description="Rankings based on overall KDR, ADR, Average First Kills per Match, and Win Rate.",
        color=0x3498db
    )
    embed.add_field(name="KDR Ranking", value=f"```{ranking_kdr}```", inline=False)
    embed.add_field(name="ADR Ranking", value=f"```{ranking_adr}```", inline=False)
    embed.add_field(name="Avg First Kills Ranking", value=f"```{ranking_first}```", inline=False)
    embed.add_field(name="Win Rate Ranking", value=f"```{ranking_win}```", inline=False)

    await ctx.send(embed=embed)


@bot.command(name="arca")
async def arca(ctx):
    """
    !arca
    Aggregates the group’s performance on each map (for the current month) using match files in the
    "matches" folder. Only matches that have at least 3 group players on one team are considered, and if group players appear on both teams, the match is skipped.
    The command computes per-map win rate, KDR, and ADR.
    """
    import os, json
    from datetime import datetime
    from discord import Embed

    # Load members.json and build a set of group GC ids.
    members_file = "members.json"
    if not os.path.exists(members_file):
        await ctx.send("members.json not found in root folder.")
        return

    with open(members_file, "r") as f:
        members_data = json.load(f)
    group_gc_ids = set()
    for discord_id, info in members_data.items():
        gc = info.get("gc")
        if gc:
            group_gc_ids.add(str(gc))
    if not group_gc_ids:
        await ctx.send("No group GC ids found in members.json.")
        return

    # Get current month/year.
    month_year = datetime.now().strftime("%Y-%m")

    # Get unique match files from the "matches" folder.
    matches_folder = "matches"
    if not os.path.isdir(matches_folder):
        await ctx.send("Matches folder not found.")
        return
    match_files = [os.path.join(matches_folder, f) for f in os.listdir(matches_folder) if f.endswith(".json")]

    # We'll aggregate stats per map.
    # For each map, we accumulate: matches, wins, kills, deaths, damage, rounds.
    group_maps = {}
    counted_matches = set()  # to ensure each match is counted only once

    for file_path in match_files:
        try:
            with open(file_path, "r") as f:
                match_data = json.load(f)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        # Check match date (assumed in top-level "data" field with format "dd/mm/YYYY HH:MM")
        match_date_str = match_data.get("data")
        if not match_date_str:
            continue
        try:
            match_date = datetime.strptime(match_date_str, "%d/%m/%Y %H:%M")
        except Exception as e:
            continue
        if match_date.strftime("%Y-%m") != month_year:
            continue

        # Get unique match id from file or filename.
        match_id = match_data.get("id") or match_data.get("match_id")
        if not match_id:
            match_id = os.path.splitext(os.path.basename(file_path))[0]
        if match_id in counted_matches:
            continue
        counted_matches.add(match_id)

        # In the match JSON, stats are under "jogos" -> "players"
        jogos = match_data.get("jogos", {})
        map_name = jogos.get("map_name", "unknown")
        players_data = jogos.get("players", {})

        # For each team, count how many players belong to our group.
        team_group_counts = {}  # e.g., {"team_a": 0, "team_b": 0}
        team_group_stats = {}   # aggregate stats for group players per team
        for team in ["team_a", "team_b"]:
            group_count = 0
            stats_sum = {"kills": 0, "deaths": 0, "damage": 0, "rounds": 0}
            for p in players_data.get(team, []):
                # p.get("idplayer") is the GC id for that player.
                if str(p.get("idplayer")) in group_gc_ids:
                    group_count += 1
                    try:
                        stats_sum["kills"] += int(p.get("nb_kill", 0))
                        stats_sum["deaths"] += int(p.get("death", 0))
                        stats_sum["damage"] += int(p.get("damage", 0))
                        stats_sum["rounds"] += int(p.get("rounds_played", 0))
                    except Exception:
                        pass
            team_group_counts[team] = group_count
            team_group_stats[team] = stats_sum

        # Determine on which team the group is present.
        teams_with_group = [team for team, count in team_group_counts.items() if count > 0]
        # Skip match if group players are on both teams or not present at all.
        if len(teams_with_group) != 1:
            continue
        team = teams_with_group[0]
        # Only count match if there are at least 3 group players.
        if team_group_counts[team] < 3:
            continue

        # Determine winning team using scores.
        try:
            score_a = int(jogos.get("score_a", "0"))
            score_b = int(jogos.get("score_b", "0"))
        except Exception:
            score_a, score_b = 0, 0
        winning_team = None
        if score_a > score_b:
            winning_team = "team_a"
        elif score_b > score_a:
            winning_team = "team_b"
        match_win = 1 if (winning_team == team) else 0

        # Aggregate stats for this match under the map.
        if map_name not in group_maps:
            group_maps[map_name] = {"matches": 0, "wins": 0, "kills": 0, "deaths": 0, "damage": 0, "rounds": 0}
        group_maps[map_name]["matches"] += 1
        group_maps[map_name]["wins"] += match_win
        group_maps[map_name]["kills"] += team_group_stats[team]["kills"]
        group_maps[map_name]["deaths"] += team_group_stats[team]["deaths"]
        group_maps[map_name]["damage"] += team_group_stats[team]["damage"]
        group_maps[map_name]["rounds"] += team_group_stats[team]["rounds"]

    if not group_maps:
        await ctx.send("No qualifying group matches found for this month.")
        return

    # Build the output: for each map, compute win rate, KDR, and ADR.
    output_lines = []
    for map_name, stats in group_maps.items():
        matches = stats["matches"]
        wins = stats["wins"]
        win_rate = (wins / matches * 100) if matches > 0 else 0
        kills = stats["kills"]
        deaths = stats["deaths"]
        damage = stats["damage"]
        rounds = stats["rounds"]
        kdr = kills / deaths if deaths > 0 else kills
        adr = damage / rounds if rounds > 0 else 0
        line = (f"**{map_name}**:\n"
                f"Matches: {matches}, Wins: {wins} (Win Rate: {win_rate:.2f}%)\n"
                f"KDR: {kdr:.2f}, ADR: {adr:.2f}\n")
        output_lines.append(line)
    output = "\n".join(output_lines)

    embed = Embed(
        title=f"Group (Arca) Performance on Each Map ({month_year})",
        description=output,
        color=0x1abc9c
    )
    await ctx.send(embed=embed)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("------")
    for guild in bot.guilds:
        print(f"Server: {guild.name} (ID: {guild.id})")
        bot_member = guild.me
        permissions = bot_member.guild_permissions
        print("Bot Permissions:")
        for perm, value in permissions:
            print(f"- {perm}: {value}")
        print("------")

if __name__ == '__main__':
    TOKEN = getpass.getpass("Enter your Discord token: ")
    bot.run(TOKEN)
