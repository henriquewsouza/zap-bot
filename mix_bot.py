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
import os
from openai import OpenAI
import logging

# ---------------------------
# Configuration
# ---------------------------

# Discord Bot Configuration
BOT_ADMINS = [291617683416285194, 701661704844738580]
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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



import logging
import os

def generate_chatgpt_summary(stats_data, player_name, all_players_data):
    """
    Gera um resumo (com elogios e roasting) baseado nos stats do player usando a nova interface da API do OpenAI.
    """
    prompt = f"""
Você é um analista de estatísticas de CS. Escreva um resumo sobre o jogador {player_name}.
Baseado nos stats:

- KDR: {stats_data.get('KDR', 0):.2f}
- ADR: {stats_data.get('ADR', 0):.2f}
- Win Rate: {stats_data.get('overall_win_rate', 0):.2f}%
- First Kills por partida: {stats_data.get('average_first_kills_per_match', 0):.2f}
- HS%: {stats_data.get('HS_percent', 0):.2f}%

Compare com a média dos outros jogadores se achar relevante.
Comente sobre os pontos fortes e fracos, elogie quando for adequado e faça uma zoada sádica e irônica, principalmente nas áreas que estão ruins.
Não evite termos provocativos.
    """
    
    try:
        logging.debug("Enviando prompt para ChatGPT: %s", prompt)
        response = client.responses.create(
            model="gpt-4o",
            instructions="Você é um analista de estatísticas de CS, sarcástico e provocador.",
            input=prompt,
            temperature=0.9,
            max_tokens=1500
        )
        logging.debug("Resposta recebida: %s", response)
        return response.output_text.strip()
    except Exception as e:
        logging.exception("Erro ao gerar o resumo com ChatGPT:")
        return "Erro ao gerar o resumo com o ChatGPT 🧠."


def split_string(text, chunk_size=1024):
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]


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

@bot.command(name="zapIA")
async def zap_ia(ctx, *, question: str):
    """
    !zapIA <pergunta>
    Envia uma pergunta ao ChatGPT baseada nas estatísticas agregadas dos jogadores do mês atual.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    await ctx.send("Processando os dados e consultando o ZapIA... 🤖")

    # Carregar members.json do S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception as e:
        await ctx.send("Erro ao carregar dados dos membros do S3.")
        return

    # Coletar estatísticas dos jogadores do mês atual
    month_year = datetime.now().strftime("%Y-%m")
    aggregated_stats = {}

    for discord_id, info in members_data.items():
        gc_id = info.get("gc")
        nickname = info.get("nickname", "Unknown")
        if not gc_id:
            continue

        stats_key = f"players/{gc_id}/stats-{month_year}.json"
        try:
            stats_response = s3.get_object(Bucket=BUCKET_NAME, Key=stats_key)
            stats_contents = stats_response["Body"].read().decode("utf-8")
            stats = json.loads(stats_contents)
            aggregated_stats[nickname] = stats
        except ClientError:
            continue
        except Exception:
            continue

    if not aggregated_stats:
        await ctx.send("Nenhum dado agregado encontrado para os jogadores este mês.")
        return

    # Enviar pergunta para o ChatGPT
    system_prompt = (
        "Você é um assistente que entende de estatísticas de CS."
        " Responda com base nas estatísticas fornecidas."
        " Use comparações, elogios e humor leve se possível."
    )

    user_message = f"Estatísticas dos jogadores:\n{json.dumps(aggregated_stats, indent=2)}\n\nPergunta: {question}"

    try:
        import openai
        openai.api_key = OPENAI_API_KEY

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.9,
            max_tokens=500
        )

        answer = response["choices"][0]["message"]["content"]

    except Exception as e:
        await ctx.send("Erro ao consultar o ChatGPT.")
        return

    # Enviar resposta formatada
    if len(answer) > 1900:
        for i in range(0, len(answer), 1900):
            await ctx.send(f"```{answer[i:i+1900]}```")
    else:
        await ctx.send(f"```{answer}```")

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
    Retrieves aggregated stats for the mentioned player for the current month from S3.
    Overall stats include total matches, wins, losses, win rate, kills, deaths,
    overall KDR, overall ADR, total first kills, average first kills per match, and HS%.
    Per-map stats include the number of matches, win rate, KDR, and ADR for each map.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception as e:
        await ctx.send("Error loading members data from S3.")
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

    month_year = datetime.now().strftime("%Y-%m")
    # Construct the S3 key for the aggregated stats file (e.g., players/{gc_id}/stats-YYYY-MM.json)
    stats_key = f"players/{gc_id}/stats-{month_year}.json"
    try:
        stats_response = s3.get_object(Bucket=BUCKET_NAME, Key=stats_key)
        stats_contents = stats_response["Body"].read().decode("utf-8")
        stats_data = json.loads(stats_contents)
    except ClientError as e:
        await ctx.send(f"Stats for {member.display_name} for {month_year} are not available on S3.")
        return
    except Exception as e:
        await ctx.send("Error loading the stats file from S3.")
        return

    # Build an embed to display overall stats.
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

    # Build per-map stats output.
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

            kdr = kills / deaths if deaths > 0 else kills
            adr = damage / rounds if rounds > 0 else 0

            per_map_str += (
                f"**{map_name}**: Matches: {matches}, Win Rate: {win_rate:.2f}%, "
                f"KDR: {kdr:.2f}, ADR: {adr:.2f}\n"
            )
    else:
        per_map_str = "No per-map stats available."

    per_map_chunks = split_string(per_map_str, 1024)
    for i, chunk in enumerate(per_map_chunks):
        field_name = "Per Map Stats" if i == 0 else f"Per Map Stats (cont.)"
        embed.add_field(name=field_name, value=chunk, inline=False)

    all_stats = {}
    for discord_id, info in members_data.items():
        gc = info.get("gc")
        if not gc or str(gc) == str(gc_id):
            continue
        other_key = f"players/{gc}/stats-{month_year}.json"
        try:
            other_response = s3.get_object(Bucket=BUCKET_NAME, Key=other_key)
            other_contents = other_response["Body"].read().decode("utf-8")
            other_stats = json.loads(other_contents)
            all_stats[info.get("nickname", "Unknown")] = other_stats
        except Exception:
            continue

    summary_text = generate_chatgpt_summary(stats_data, member.display_name, all_stats)
    embed.add_field(name="🧠 ZapIA ", value=summary_text, inline=False)
    await ctx.send(embed=embed)


@bot.command(name="update")
@commands.check(lambda ctx: ctx.author.id in BOT_ADMINS)
async def update(ctx, member: discord.Member):
    """
    !update @Member
    Updates the stats for the mentioned member for the current month.
    This command will:
      1. Retrieve the member's match history from the API and upload it to S3.
      2. Download full match stats for each match (ensuring they are stored on S3).
      3. Aggregate the match stats and upload the aggregated file to S3.
    """
    import asyncio
    from datetime import datetime
    from match_history import get_match_history
    from load_match_stats import load_match_stats
    from aggregate_player_stats import aggregate_stats

    # Use the global user_levels loaded from S3.
    member_id = member.id
    if member_id not in user_levels:
        await ctx.send(f"{member.display_name} is not in the members list.")
        return

    gc_id = user_levels[member_id].get("gc")
    if not gc_id:
        await ctx.send(f"{member.display_name} does not have a GC id set.")
        return

    month_year = datetime.now().strftime("%Y-%m")
    await ctx.send(f"Updating stats for {member.mention} (GC: {gc_id}) for {month_year} ...")

    def process_member(gc_id, month_year):
        # get_match_history uploads match history to S3 and returns the S3 key.
        history_key = get_match_history(gc_id, month_year)
        # load_match_stats downloads match stats for each match (via subprocess) using S3.
        load_match_stats(history_key)
        # aggregate_stats aggregates the match stats and uploads the aggregated JSON to S3.
        aggregate_stats(gc_id, month_year)

    await asyncio.to_thread(process_member, gc_id, month_year)
    await ctx.send(f"Update complete for {member.mention}.")



@bot.command(name="ranking")
async def ranking(ctx):
    """
    !ranking
    Displays a ranking of members (from members.json stored on S3) for the current month,
    based on overall KDR, ADR, average first kills per match, and overall win rate.
    Each ranking shows the member's nickname, metric value, and total matches played.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception as e:
        await ctx.send("Error loading members data from S3.")
        return

    month_year = datetime.now().strftime("%Y-%m")
    stats_list = []

    # Iterate over each member in members.json
    for discord_id, info in members_data.items():
        gc_id = info.get("gc")
        if not gc_id:
            continue
        stats_key = f"players/{gc_id}/stats-{month_year}.json"
        try:
            stats_response = s3.get_object(Bucket=BUCKET_NAME, Key=stats_key)
            stats_contents = stats_response["Body"].read().decode("utf-8")
            stats = json.loads(stats_contents)
        except ClientError:
            continue  # Skip members with no stats file
        except Exception:
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

    # Helper: Build ranking string from a sorted list
    def build_ranking_str(sorted_list, metric_key, metric_name):
        lines = []
        for idx, stat in enumerate(sorted_list, start=1):
            value = stat[metric_key]
            lines.append(f"{idx}. {stat['nickname']} - {metric_name}: {value:.2f} ({stat['matches']} matches)")
        return "\n".join(lines)

    # Sort members by each metric (descending: higher is better)
    kdr_sorted = sorted(stats_list, key=lambda x: x["kdr"], reverse=True)
    adr_sorted = sorted(stats_list, key=lambda x: x["adr"], reverse=True)
    first_sorted = sorted(stats_list, key=lambda x: x["avg_first"], reverse=True)
    win_rate_sorted = sorted(stats_list, key=lambda x: x["win_rate"], reverse=True)

    ranking_kdr = build_ranking_str(kdr_sorted, "kdr", "KDR")
    ranking_adr = build_ranking_str(adr_sorted, "adr", "ADR")
    ranking_first = build_ranking_str(first_sorted, "avg_first", "Avg First Kills")
    ranking_win = build_ranking_str(win_rate_sorted, "win_rate", "Win Rate")

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
    Aggregates the group's performance on each map for the current month using match data stored in S3.
    Only counts matches where group players (from members.json on S3) appear on exactly one team and at least 3 are present.
    Displays per-map win rate (with a bar), KDR, and ADR.
    """
    import json
    from datetime import datetime
    from discord import Embed
    from botocore.exceptions import ClientError

    # Helper: Create a simple bar for a percentage.
    def create_bar(percentage, length=10):
        filled_length = int(round(length * percentage / 100))
        bar = "█" * filled_length + "─" * (length - filled_length)
        return bar

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception as e:
        await ctx.send("Error loading members data from S3.")
        return

    # Build a set of group GC ids (as strings)
    group_gc_ids = {str(info.get("gc")) for info in members_data.values() if info.get("gc")}
    if not group_gc_ids:
        await ctx.send("No group GC ids found in members data.")
        return

    month_year = datetime.now().strftime("%Y-%m")

    # List match objects from S3 with prefix "matches/"
    try:
        list_response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="matches/")
    except Exception as e:
        await ctx.send("Error listing match objects from S3.")
        return
    objects = list_response.get("Contents", [])
    if not objects:
        await ctx.send("No match objects found in S3.")
        return

    group_maps = {}  # Will accumulate per-map stats
    counted_matches = set()  # To ensure each match is counted only once

    for obj in objects:
        key = obj["Key"]
        try:
            obj_response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
            contents = obj_response["Body"].read().decode("utf-8")
            match_data = json.loads(contents)
        except Exception as e:
            print(f"Error reading {key}: {e}")
            continue

        # Filter by match date (assumed in top-level "data" field with format "dd/mm/YYYY HH:MM")
        match_date_str = match_data.get("data")
        if not match_date_str:
            continue
        try:
            match_date = datetime.strptime(match_date_str, "%d/%m/%Y %H:%M")
        except Exception:
            continue
        if match_date.strftime("%Y-%m") != month_year:
            continue

        # Determine unique match id
        match_id = match_data.get("id") or match_data.get("match_id")
        if not match_id:
            match_id = key.split("/")[-1].split(".")[0]
        if match_id in counted_matches:
            continue
        counted_matches.add(match_id)

        # Get players data from "jogos" -> "players"
        jogos = match_data.get("jogos", {})
        map_name = jogos.get("map_name", "unknown")
        players_data = jogos.get("players", {})

        # Count group players and sum stats per team.
        team_group_counts = {}
        team_group_stats = {}
        for team in ["team_a", "team_b"]:
            count = 0
            stats_sum = {"kills": 0, "deaths": 0, "damage": 0, "rounds": 0}
            for p in players_data.get(team, []):
                if str(p.get("idplayer")) in group_gc_ids:
                    count += 1
                    try:
                        stats_sum["kills"] += int(p.get("nb_kill", 0))
                        stats_sum["deaths"] += int(p.get("death", 0))
                        stats_sum["damage"] += int(p.get("damage", 0))
                        stats_sum["rounds"] += int(p.get("rounds_played", 0))
                    except Exception:
                        pass
            team_group_counts[team] = count
            team_group_stats[team] = stats_sum

        # Only count if group players appear on exactly one team.
        teams_with_group = [team for team, count in team_group_counts.items() if count > 0]
        if len(teams_with_group) != 1:
            continue
        team = teams_with_group[0]
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

        # Aggregate stats per map.
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

    # Sort maps by number of matches played (most played first)
    sorted_maps = sorted(group_maps.items(), key=lambda x: x[1]["matches"], reverse=True)
    output_lines = []
    for map_name, stats in sorted_maps:
        matches = stats["matches"]
        wins = stats["wins"]
        win_rate = (wins / matches * 100) if matches > 0 else 0
        kills = stats["kills"]
        deaths = stats["deaths"]
        damage = stats["damage"]
        rounds = stats["rounds"]
        kdr = kills / deaths if deaths > 0 else kills
        adr = damage / rounds if rounds > 0 else 0

        # Create a win rate bar (length 10)
        bar = create_bar(win_rate, length=10)
        line = (
            f"**{map_name}**:\n"
            f"Matches: {matches} | Wins: {wins} (Win Rate: {win_rate:.2f}% {bar})\n"
            f"KDR: {kdr:.2f} | ADR: {adr:.2f}\n"
        )
        output_lines.append(line)
    output = "\n".join(output_lines)

    embed = Embed(
        title=f"Group (Arca) Performance on Each Map ({month_year})",
        description=output,
        color=0x1abc9c
    )
    await ctx.send(embed=embed)


@bot.command(name="updateall")
@commands.check(lambda ctx: ctx.author.id in BOT_ADMINS)
async def updateall(ctx):
    """
    !updateall
    Updates the stats for all players listed in members.json.
    For each member, it:
      1. Retrieves the member's match history from the API and uploads it to S3.
      2. Downloads full match stats for each match (ensuring they're stored on S3).
      3. Aggregates the match stats and uploads the aggregated file to S3.
    This command is restricted to bot admins.
    """
    import json, asyncio
    from datetime import datetime
    from match_history import get_match_history
    from load_match_stats import load_match_stats
    from aggregate_player_stats import aggregate_stats

    await ctx.send("Starting update for all players. This may take a while...")

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception as e:
        await ctx.send("Error loading members data from S3.")
        return

    month_year = datetime.now().strftime("%Y-%m")
    
    # Process each member sequentially
    for discord_id, info in members_data.items():
        gc_id = info.get("gc")
        if not gc_id:
            continue  # Skip if no GC id is set
        await ctx.send(f"Updating stats for GC id: {gc_id}...")
        
        def process_member(gc_id, month_year):
            # Retrieve match history from API and upload to S3.
            history_key = get_match_history(gc_id, month_year)
            # For each match in the history, ensure full match stats are on S3.
            load_match_stats(history_key)
            # Aggregate the match stats and upload the aggregated data to S3.
            aggregate_stats(gc_id, month_year)
        
        # Run blocking operations in a background thread.
        await asyncio.to_thread(process_member, gc_id, month_year)
    
    await ctx.send("Update complete for all players.")

@bot.command(name="ranking_mix")
async def ranking_mix(ctx):
    """
    !ranking_mix
    Generates leaderboards for matches where BOTH teams have at least 1 group player.
    Only these matches count towards each player's stats (KDR, ADR, etc.).
    Displays a ranking of group players by KDR, ADR, Avg First Kills, and Win Rate.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    # Step 1: Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception as e:
        await ctx.send("Error loading members data from S3.")
        return

    # Build a dictionary: {discord_id_str: gc_id_str}
    discord_to_gc = {}
    for discord_id_str, info in members_data.items():
        gc_id = info.get("gc")
        if gc_id:
            discord_to_gc[discord_id_str] = str(gc_id)

    if not discord_to_gc:
        await ctx.send("No group GC ids found in members data.")
        return

    month_year = datetime.now().strftime("%Y-%m")

    # Step 2: List match objects from S3 with prefix "matches/"
    try:
        list_response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="matches/")
    except Exception as e:
        await ctx.send("Error listing match objects from S3.")
        return
    objects = list_response.get("Contents", [])
    if not objects:
        await ctx.send("No match objects found in S3.")
        return

    # We'll accumulate stats per GC ID
    # mix_stats[gc_id] = { "kills":0, "deaths":0, "damage":0, "rounds":0, "wins":0, "matches":0, "first_kills":0 }
    mix_stats = {}

    def ensure_player(gc):
        """Helper to initialize a player's stats in mix_stats if not present."""
        if gc not in mix_stats:
            mix_stats[gc] = {
                "kills": 0,
                "deaths": 0,
                "damage": 0,
                "rounds": 0,
                "wins": 0,
                "matches": 0,
                "first_kills": 0
            }

    counted_matches = set()

    # Step 3: Parse each match object
    for obj in objects:
        key = obj["Key"]
        try:
            obj_response = s3.get_object(Bucket=BUCKET_NAME, Key=key)
            contents = obj_response["Body"].read().decode("utf-8")
            match_data = json.loads(contents)
        except Exception as e:
            print(f"Error reading {key}: {e}")
            continue

        # Filter by match date (top-level "data" field, format "dd/mm/YYYY HH:MM")
        match_date_str = match_data.get("data")
        if not match_date_str:
            continue
        try:
            match_date = datetime.strptime(match_date_str, "%d/%m/%Y %H:%M")
        except Exception:
            continue

        if match_date.strftime("%Y-%m") != month_year:
            continue

        match_id = match_data.get("id") or match_data.get("match_id")
        if not match_id:
            match_id = key.split("/")[-1].split(".")[0]
        if match_id in counted_matches:
            continue
        counted_matches.add(match_id)

        jogos = match_data.get("jogos", {})
        players_data = jogos.get("players", {})
        score_a = int(jogos.get("score_a", 0))
        score_b = int(jogos.get("score_b", 0))
        winning_team = None
        if score_a > score_b:
            winning_team = "team_a"
        elif score_b > score_a:
            winning_team = "team_b"

        # Step 4: Check how many group players on team_a vs team_b
        team_a_group = []
        team_b_group = []
        for p in players_data.get("team_a", []):
            gc = str(p.get("idplayer"))
            if gc in discord_to_gc.values():
                team_a_group.append(p)
        for p in players_data.get("team_b", []):
            gc = str(p.get("idplayer"))
            if gc in discord_to_gc.values():
                team_b_group.append(p)

        # We only consider matches if both teams have >= 1 group player
        if not team_a_group or not team_b_group:
            continue

        # Step 5: For each group player in the match, accumulate stats
        # If that player's team is the winner, increment wins
        # Also accumulate kills, deaths, damage, rounds, first_kills
        for p in team_a_group:
            gc = str(p.get("idplayer"))
            ensure_player(gc)
            mix_stats[gc]["matches"] += 1
            # Kills, deaths, damage, rounds, first kills
            try:
                mix_stats[gc]["kills"] += int(p.get("nb_kill", 0))
                mix_stats[gc]["deaths"] += int(p.get("death", 0))
                mix_stats[gc]["damage"] += int(p.get("damage", 0))
                mix_stats[gc]["rounds"] += int(p.get("rounds_played", 0))
                mix_stats[gc]["first_kills"] += int(p.get("firstkill", 0))
            except Exception:
                pass
            if winning_team == "team_a":
                mix_stats[gc]["wins"] += 1

        for p in team_b_group:
            gc = str(p.get("idplayer"))
            ensure_player(gc)
            mix_stats[gc]["matches"] += 1
            # Kills, deaths, damage, rounds, first kills
            try:
                mix_stats[gc]["kills"] += int(p.get("nb_kill", 0))
                mix_stats[gc]["deaths"] += int(p.get("death", 0))
                mix_stats[gc]["damage"] += int(p.get("damage", 0))
                mix_stats[gc]["rounds"] += int(p.get("rounds_played", 0))
                mix_stats[gc]["first_kills"] += int(p.get("firstkill", 0))
            except Exception:
                pass
            if winning_team == "team_b":
                mix_stats[gc]["wins"] += 1

    # Step 6: Build final ranking
    # For each group player in mix_stats, compute KDR, ADR, average first kills, and overall win rate
    if not mix_stats:
        await ctx.send("No 'mix' matches found this month (where both teams had group players).")
        return

    # Build a list of players with computed metrics
    players_list = []
    for gc, data in mix_stats.items():
        kills = data["kills"]
        deaths = data["deaths"]
        damage = data["damage"]
        rounds = data["rounds"]
        matches = data["matches"]
        wins = data["wins"]
        first_kills = data["first_kills"]

        kdr = kills / deaths if deaths > 0 else float(kills)
        adr = damage / rounds if rounds > 0 else 0
        avg_first = first_kills / matches if matches > 0 else 0
        win_rate = (wins / matches * 100) if matches > 0 else 0

        # Find the matching discord_id to get nickname
        # We do a reverse lookup of gc => discord_id from discord_to_gc
        # Then we get the nickname from members_data
        # or default to f"Unknown({gc})"
        discord_id_found = None
        for disc_id_str, info in members_data.items():
            if str(info.get("gc")) == gc:
                discord_id_found = disc_id_str
                break

        nickname = f"Unknown({gc})"
        if discord_id_found and "nickname" in members_data[discord_id_found]:
            nickname = members_data[discord_id_found]["nickname"]

        players_list.append({
            "gc_id": gc,
            "discord_id": discord_id_found,
            "nickname": nickname,
            "kdr": kdr,
            "adr": adr,
            "avg_first": avg_first,
            "win_rate": win_rate,
            "matches": matches
        })

    if not players_list:
        await ctx.send("No group player data found in mix matches this month.")
        return

    # Helper to build ranking string
    def build_ranking_str(sorted_list, metric_key, metric_name):
        lines = []
        for idx, stat in enumerate(sorted_list, start=1):
            value = stat[metric_key]
            lines.append(f"{idx}. {stat['nickname']} - {metric_name}: {value:.2f} ({stat['matches']} matches)")
        return "\n".join(lines)

    # Sort by each metric in descending order
    kdr_sorted = sorted(players_list, key=lambda x: x["kdr"], reverse=True)
    adr_sorted = sorted(players_list, key=lambda x: x["adr"], reverse=True)
    first_sorted = sorted(players_list, key=lambda x: x["avg_first"], reverse=True)
    win_rate_sorted = sorted(players_list, key=lambda x: x["win_rate"], reverse=True)

    ranking_kdr = build_ranking_str(kdr_sorted, "kdr", "KDR")
    ranking_adr = build_ranking_str(adr_sorted, "adr", "ADR")
    ranking_first = build_ranking_str(first_sorted, "avg_first", "Avg First Kills")
    ranking_win = build_ranking_str(win_rate_sorted, "win_rate", "Win Rate")

    embed = discord.Embed(
        title=f"**Mix Ranking** - {month_year}",
        description=(
            "These stats are taken **only** from matches where both teams "
            "had at least one group player.\n"
            "Metrics: KDR, ADR, Average First Kills, and Win Rate."
        ),
        color=0x9b59b6
    )
    embed.add_field(name="KDR Ranking", value=f"```{ranking_kdr}```", inline=False)
    embed.add_field(name="ADR Ranking", value=f"```{ranking_adr}```", inline=False)
    embed.add_field(name="Avg First Kills Ranking", value=f"```{ranking_first}```", inline=False)
    embed.add_field(name="Win Rate Ranking", value=f"```{ranking_win}```", inline=False)

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
    OPENAI_API_KEY = getpass.getpass("Enter your OpenAI API key: ")
    client = OpenAI(
    # This is the default and can be omitted
    api_key=os.environ.get("OPENAI_API_KEY"),
    )
    bot.run(TOKEN)
