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
import logging
import openai
from openai import OpenAI
import json
from ranking_mix_handler import RankingMixHandler
from ranking_creator_handler import RankingCreatorHandler
from vintao_stats_handler import VintaoLocalStatsHandler
from ranking_handler import RankingHandler
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

ANNOUNCE_CHANNEL_ID = 1395712364472700939  # canal “avisos‑de‑jogo”

# Create an S3 client using the custom endpoint
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)
ranking_mix_handler = RankingMixHandler(s3, BUCKET_NAME, OBJECT_KEY)
HIDDEN_ZAP_GOD_ID = 0
creator_handler = RankingCreatorHandler(s3, BUCKET_NAME, OBJECT_KEY)
vintao_local = VintaoLocalStatsHandler()
ranking_handler = RankingHandler(s3, BUCKET_NAME, OBJECT_KEY)  # NOVO

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

# ---------------------------
# Level Helpers
# ---------------------------

def get_effective_level(member):
    """
    For balancing: use hidden override for Zap God,
    otherwise use stored level.
    """
    if member.id == "0":
        return 12
    return user_levels.get(member.id, {}).get('level', 0)


def get_display_level(member):
    """
    For display: always use the stored level (actual).
    """
    return user_levels.get(member.id, {}).get('level', 0)

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
    sorted_team1 = sorted(team1, key=lambda m: get_display_level(m), reverse=True)
    sorted_team2 = sorted(team2, key=lambda m: get_display_level(m), reverse=True)

    total_team1 = sum(get_display_level(m) for m in sorted_team1)
    total_team2 = sum(get_display_level(m) for m in sorted_team2)

    team1_text = "\n".join(
        f"{m.mention} (Level: {get_display_level(m)})" for m in sorted_team1
    )
    team2_text = "\n".join(
        f"{m.mention} (Level: {get_display_level(m)})" for m in sorted_team2
    )

    message = (
        f"**Team 1:**\n{team1_text}\n\n"
        f"**Team 2:**\n{team2_text}\n\n"
        f"**Lembre-se: Se vc sacanear o Zap é melhor esperar que ele não descubra seu IP**"
    )
    return message


def generate_valid_partitions(members):
    """
    Generate all valid team partitions, balancing by effective levels.
    """
    partitions = []
    n = len(members)
    team1_size = n // 2
    for team1 in itertools.combinations(members, team1_size):
        team2 = [m for m in members if m not in team1]
        total1 = sum(get_effective_level(m) for m in team1)
        total2 = sum(get_effective_level(m) for m in team2)
        diff = abs(total1 - total2)
        partitions.append((diff, team1, team2))
    return partitions


async def send_mix_result(channel, team1, team2):
    """
    Sends the generated team partition result to the specified channel.
    """
    message = build_team_message(team1, team2)
    await channel.send("**Teams Generated:**\n" + message)

# ---------------------------
# Parsing Helpers for Mix Command (Updated)
# ---------------------------

async def parse_mix_args(ctx):
    """
    Parse command arguments from ctx.message.content.
    Expected format:
      !mix [<number>] [--exclude or -e] <member mentions> [--extra or -x] <member mentions> [--duelo or -t] <member mentions>
    Returns a tuple: (combination_count, exclusions, extras, duelo)
    """
    args = ctx.message.content.split()[1:]  # skip the command name
    combination_count = 1  # default value
    if args and args[0].isdigit():
        combination_count = int(args[0])
        args = args[1:]
    
    mode = None
    exclusions = []
    extras = []
    duelo = []
    converter = commands.MemberConverter()
    for arg in args:
        if arg.lower() in ("-e", "--exclude"):
            mode = "exclude"
        elif arg.lower() in ("-x", "--extra"):
            mode = "extra"
        elif arg.lower() in ("-t", "--duelo"):
            mode = "duelo"
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
            elif mode == "duelo":
                duelo.append(member)
    return combination_count, exclusions, extras, duelo

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

def generate_chatgpt_summary(stats_data, player_name, leaderboard_summary, context):
    """
    Gera um resumo conciso (com elogios e roast) baseado nos stats do jogador,
    comparando-os com os dados gerais (leaderboard_summary).
    """
    prompt = f"""
Você é um analista de estatísticas de CS. Escreva um resumo conciso sobre o jogador {player_name} com base nos seguintes stats:
- KDR: {stats_data.get('KDR', 0):.2f}
- ADR: {stats_data.get('ADR', 0):.2f}
- Win Rate: {stats_data.get('overall_win_rate', 0):.2f}%
- First Kills por partida: {stats_data.get('average_first_kills_per_match', 0):.2f}
- HS%: {stats_data.get('HS_percent', 0):.2f}

Compare esses números com a média do grupo (leaderboard):
{leaderboard_summary}
Contexto do jogador: {context}

Se os números forem bons, elogie de forma sincera; se forem ruins, faça uma zoada extremamente ofensiva, usando termos chulos, provocativa, irônica e incisiva. Seja breve e direto. Os roast precisam ter comparações com outros membros. Não compare sempre com os bons, foque nos ruins também, "Olha ai, até tal player é melhor que vc nisso!", use criatividade. Veja sempre onde a pessoa está nas médias, por exemplo first kills abaixo de 2.3 normalmente é ruim! não precisa bater stats por stats, escreva um resumo livre! Não compare somente com o primeiro e o ultimo das listas, faça com jogadores do meio também. Seja criativo no uso do context para que não fique repetitivo ao gerar outras vezes.
    """
    try:
        logging.debug("Enviando prompt para ChatGPT: %s", prompt)
        response = client.responses.create(
            model="gpt-4o",
            instructions="Você é um analista de estatísticas de CS, conciso, sarcástico e provocador.",
            input=prompt
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
    !mix [<number>] [--exclude @User ...] [--extra @User ...] [--duelo @User @User]
    Generates one or more balanced team partitions from non‑bot members.
    With --duelo flag, the two specified members will not be placed on the same team.
    Additionally, if the requester is not a bot admin, they cannot be one of the duelo members.
    """
    global mix_in_progress
    if mix_in_progress:
        await ctx.send("A team mix is already in progress. Please wait until it is finished.")
        return

    mix_in_progress = True
    try:
        channel = ctx.channel
        combination_count, exclusions, extras, duelo = await parse_mix_args(ctx)
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
        
        # Apply the --duelo flag if provided
        if duelo:
            if len(duelo) != 2:
                await channel.send("Please provide exactly 2 members for the --duelo flag.")
                return
            # Non-bot-admin users cannot include themselves as one of the duelo parameters.
            if ctx.author.id not in BOT_ADMINS and any(member.id == ctx.author.id for member in duelo):
                await channel.send("You cannot use --duelo flag with yourself as one of the parameters.")
                return

            # Helper function to check if a member is in a team (by comparing IDs).
            def in_team(team, member):
                return any(m.id == member.id for m in team)
            
            # Filter out partitions where both duelo members end up on the same team.
            partitions = [
                p for p in partitions 
                if not (
                    (in_team(p[1], duelo[0]) and in_team(p[1], duelo[1])) or 
                    (in_team(p[2], duelo[0]) and in_team(p[2], duelo[1]))
                )
            ]

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

@bot.command(name="ranking_creators")
async def ranking_creators(ctx, *, args: str = None):
    """
    !ranking_creators [YYYY-MM | -all]
    Ranking de win‑rate dos criadores de lobby.
    """
    await creator_handler.handle(ctx, args)


@bot.command(name="meu_vintao")
async def meu_vintao(ctx):
    await vintao_local.handle(ctx)

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
    Exibe a lista de comandos disponíveis.
    """
    help_text = (
        "**Comandos do Zap Bot**\n\n"
        "__👥 Gestão de Times__\n"
        "**!mix [<n>] [--exclude/-e @User …] [--extra/-x @User …] [--duelo/-t @A @B]**\n"
        "   • Gera até **n** partições balanceadas dos membros do seu canal de voz.\n"
        "   • `--exclude` remove mencionados, `--extra` adiciona extras, `--duelo` garante que dois jogadores fiquem em lados opostos.\n"
        "**!arere** – Divide o canal de voz aleatoriamente em dois times.\n"
        "**!ranking_mix [YYYY-MM]** – Leaderboards apenas de partidas onde ambos os times tinham players do grupo.\n\n"
        "__📊 Estatísticas de Jogadores__\n"
        "**!stats @Player [YYYY-MM]** – Mostra stats do mês (ou atual) + roast gerado pelo ZapIA.\n"
        "**!alltimestats @Player** – Agrega todos os meses registrados para o jogador.\n"
        "**!ranking [YYYY-MM]** – Ranking mensal (KDR, ADR, FK, Win Rate).\n"
        "**!alltimeranking** – Ranking geral somando todos os meses.\n"
        "**!arca [YYYY-MM | -all]** – Desempenho do grupo por mapa (mês ou all-time).\n\n"
        "__🤖 Integração com IA__\n"
        "**!zapIA <pergunta>** – Pergunte qualquer coisa sobre os stats agregados do grupo; resposta vem com elogios e roast.\n\n"
        "__🔧 Comandos de Administração__ (Bot Admins)\n"
        "**!setlevel @User <level>** – Define o nível permanente do jogador.\n"
        "**!addtemp @User <level>** – Adiciona nível temporário (somente memória).\n"
        "**!clear** – Limpa todas as mensagens não fixadas do canal atual.\n"
        "**!update @User** – Atualiza histórico e stats do jogador para o mês corrente.\n"
        "**!updateall** – Atualiza histórico/stats de todos os jogadores listados.\n\n"
        "__ℹ️ Informações__\n"
        "**!players** – Lista todos os jogadores cadastrados com níveis.\n"
        "**!botadmins** – Mostra quem são os administradores do bot.\n"
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

@bot.command(name="alltimestats")
async def all_time_stats(ctx, member: discord.Member):
    """
    !alltimestats @Player
    Aggregates all available stats for the mentioned player across all months.
    """
    import json
    from botocore.exceptions import ClientError

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception:
        await ctx.send("Erro ao carregar dados dos membros do S3.")
        return

    discord_id_str = str(member.id)
    if discord_id_str not in members_data:
        await ctx.send(f"{member.display_name} não está na lista de membros.")
        return

    gc_id = members_data[discord_id_str].get("gc")
    if not gc_id:
        await ctx.send(f"{member.display_name} não tem GC ID definido.")
        return

    # List all monthly stats files for this player
    prefix = f"players/{gc_id}/stats-"
    try:
        list_resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
        files = list_resp.get("Contents", [])
    except Exception:
        await ctx.send("Erro ao listar arquivos de stats no S3.")
        return

    if not files:
        await ctx.send(f"Nenhum stats encontrado para {member.display_name}.")
        return

    # Initialize aggregate counters
    total_matches = total_wins = total_losses = 0
    total_kills = total_deaths = total_first_kills = 0
    sum_adr = sum_hs = sum_matches_for_avg = 0

    # Iterate through each stats file
    for obj in files:
        try:
            stats_data = json.loads(
                s3.get_object(Bucket=BUCKET_NAME, Key=obj['Key'])["Body"].read().decode("utf-8")
            )
        except ClientError:
            continue
        except Exception:
            continue

        matches = stats_data.get("total_matches", 0)
        total_matches += matches
        total_wins += stats_data.get("total_wins", 0)
        total_losses += stats_data.get("total_losses", 0)
        total_kills += stats_data.get("total_kills", 0)
        total_deaths += stats_data.get("total_deaths", 0)
        total_first_kills += stats_data.get("total_first_kills", 0)

        # Weighted for averages
        if matches > 0:
            sum_adr += stats_data.get("ADR", 0) * matches
            sum_hs += stats_data.get("HS_percent", 0) * matches
            sum_matches_for_avg += matches

    # Calculate aggregated metrics
    win_rate = (total_wins / total_matches * 100) if total_matches else 0
    kdr = (total_kills / total_deaths) if total_deaths else total_kills
    avg_adr = (sum_adr / sum_matches_for_avg) if sum_matches_for_avg else 0
    avg_hs = (sum_hs / sum_matches_for_avg) if sum_matches_for_avg else 0
    avg_fk = (total_first_kills / total_matches) if total_matches else 0

    # Build and send embed
    embed = discord.Embed(
        title=f"All Time Stats de {member.display_name}",
        color=0x00ff00
    )
    embed.add_field(name="Partidas", value=total_matches, inline=True)
    embed.add_field(name="Vitórias", value=total_wins, inline=True)
    embed.add_field(name="Derrotas", value=total_losses, inline=True)
    embed.add_field(name="Win Rate", value=f"{win_rate:.2f}%", inline=True)
    embed.add_field(name="Kills", value=total_kills, inline=True)
    embed.add_field(name="Deaths", value=total_deaths, inline=True)
    embed.add_field(name="KDR", value=f"{kdr:.2f}", inline=True)
    embed.add_field(name="ADR", value=f"{avg_adr:.2f}", inline=True)
    embed.add_field(name="HS%", value=f"{avg_hs:.2f}%", inline=True)
    embed.add_field(name="First Kills", value=total_first_kills, inline=True)
    embed.add_field(name="Avg FK/Match", value=f"{avg_fk:.2f}", inline=True)
    await ctx.send(embed=embed)


@bot.command(name="stats")
async def stats(ctx, member: discord.Member, month: str = None):
    """
    !stats @Player
    Recupera as estatísticas agregadas para o jogador mencionado para o mês atual (dados armazenados no S3).
    Exibe estatísticas gerais, por mapa e um resumo gerado pelo ChatGPT que compara os stats do jogador com o leaderboard.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    # Carregar members.json do S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception:
        await ctx.send("Erro ao carregar dados dos membros do S3.")
        return

    discord_id_str = str(member.id)
    if discord_id_str not in members_data:
        await ctx.send(f"{member.display_name} não está na lista de membros.")
        return

    gc_id = members_data[discord_id_str].get("gc")
    if not gc_id:
        await ctx.send(f"{member.display_name} não tem GC ID definido.")
        return

    # Extrai o campo context do membro (pode estar vazio)
    context_field = members_data[discord_id_str].get("context", "")

    if month:
        try:
            datetime.strptime(month, "%Y-%m")
            month_year = month
        except ValueError:
            await ctx.send("Use YYYY-MM format, e.g. `!ranking 2025-04`")
            return
    else:
        month_year = datetime.now().strftime("%Y-%m")

    stats_key = f"players/{gc_id}/stats-{month_year}.json"
    try:
        stats_response = s3.get_object(Bucket=BUCKET_NAME, Key=stats_key)
        stats_contents = stats_response["Body"].read().decode("utf-8")
        stats_data = json.loads(stats_contents)
    except ClientError:
        await ctx.send(f"Stats de {member.display_name} para {month_year} não disponíveis no S3.")
        return
    except Exception:
        await ctx.send("Erro ao carregar stats do S3.")
        return

    # Criação do embed com estatísticas gerais
    embed = discord.Embed(
        title=f"Stats de {member.display_name} - {month_year}",
        color=0x00ff00
    )
    embed.add_field(name="Partidas", value=stats_data.get("total_matches", 0), inline=True)
    embed.add_field(name="Vitórias", value=stats_data.get("total_wins", 0), inline=True)
    embed.add_field(name="Derrotas", value=stats_data.get("total_losses", 0), inline=True)
    embed.add_field(name="Win Rate", value=f"{stats_data.get('overall_win_rate', 0):.2f}%", inline=True)
    embed.add_field(name="Kills", value=stats_data.get("total_kills", 0), inline=True)
    embed.add_field(name="Deaths", value=stats_data.get("total_deaths", 0), inline=True)
    embed.add_field(name="KDR", value=f"{stats_data.get('KDR', 0):.2f}", inline=True)
    embed.add_field(name="ADR", value=f"{stats_data.get('ADR', 0):.2f}", inline=True)
    embed.add_field(name="First Kills", value=stats_data.get("total_first_kills", 0), inline=True)
    embed.add_field(name="Avg FK/Match", value=f"{stats_data.get('average_first_kills_per_match', 0):.2f}", inline=True)
    embed.add_field(name="HS%", value=f"{stats_data.get('HS_percent', 0):.2f}%", inline=True)

    # Estatísticas por mapa
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
            per_map_str += f"**{map_name}**: {matches} part., WR: {win_rate:.2f}%, KDR: {kdr:.2f}, ADR: {adr:.2f}\n"
    else:
        per_map_str = "Sem dados por mapa."
    embed.add_field(name="Por mapa", value=per_map_str[:1024], inline=False)

    # Gerar o leaderboard_summary com os stats dos demais jogadores
    leaderboard_data = []
    for other_id, info in members_data.items():
        other_gc = info.get("gc")
        if not other_gc or str(other_gc) == str(gc_id):
            continue
        other_key = f"players/{other_gc}/stats-{month_year}.json"
        try:
            other_stats = json.loads(s3.get_object(Bucket=BUCKET_NAME, Key=other_key)["Body"].read().decode("utf-8"))
            leaderboard_data.append((info.get("nickname", "Unknown"), other_stats.get("KDR", 0)))
        except Exception:
            continue
    leaderboard_data.sort(key=lambda x: x[1], reverse=True)
    leaderboard_summary = "Top jogadores: " + ", ".join([f"{n} (KDR: {kdr:.2f})" for n, kdr in leaderboard_data])
    
    # Gerar resumo com ChatGPT passando o campo context
    summary_text = generate_chatgpt_summary(stats_data, member.display_name, leaderboard_summary, context_field)

    await ctx.send(embed=embed)

    # Se o resumo for curto, envia em embed; caso contrário, envia em partes
    if len(summary_text) <= 1024:
        await ctx.send(embed=discord.Embed(title="🧠 ZapIA", description=summary_text, color=0x7289da))
    else:
        await ctx.send("🧠 **Resumo gerado por ZapIA:**")
        for chunk in [summary_text[i:i+1900] for i in range(0, len(summary_text), 1900)]:
            await ctx.send(f"```{chunk}```")


@bot.command(name="zapIA")
async def zap_ia(ctx, *, question: str):
    """
    !zapIA <pergunta>
    Consulta o ChatGPT com as estatísticas agregadas de todos os jogadores (mês atual),
    incluindo desempenho por mapa e informações de contexto (context) dos membros.
    Retorna uma resposta provocativa com elogios e roast. Use o contexto de forma bem discreta, se não toda vez que eu gerar perguntas vc vai ficar repetindo, apenas detalhes sutis do concept devem ser utilizados.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    await ctx.send("Processando dados dos jogadores e consultando o ZapIA... 🤖")

    # Carrega members.json do S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception:
        await ctx.send("Erro ao carregar dados dos membros do S3.")
        return

    month_year = datetime.now().strftime("%Y-%m")
    aggregated_stats = {}  # {nickname: stats}

    # Coleta os stats agregados de cada jogador
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

    # Gerar um resumo rápido do leaderboard usando os top 3 por KDR
    leaderboard_data = []
    for nickname, stats in aggregated_stats.items():
        kdr = stats.get("KDR", 0)
        leaderboard_data.append((nickname, kdr))
    leaderboard_data.sort(key=lambda x: x[1], reverse=True)
    top3 = leaderboard_data[:3]
    leaderboard_summary = "Top jogadores: " + ", ".join([f"{n} (KDR: {kdr:.2f})" for n, kdr in top3])

    # Gerar um resumo de contextos dos membros
    context_list = []
    for info in members_data.values():
        nickname = info.get("nickname", "Unknown")
        context_field = info.get("context", "")
        if context_field:
            context_list.append(f"{nickname}: {context_field}")
    context_summary = "\n".join(context_list)
    if not context_summary:
        context_summary = "Sem informações de contexto."

    # Construir o prompt para o ChatGPT, incluindo o context_summary
    prompt = f"""
Contexto geral dos membros:
{context_summary}

Dados agregados do grupo para o mês {month_year}:
{leaderboard_summary}

Pergunta: {question}

Responda de forma concisa e provocativa, elogiando onde os números estão bons e fazendo um roast extremamente ofensivo e irônico nas áreas fracas, com comparações entre os jogadores. Foque nos stats, o context deve ser apenas usados para detalhe, uma ou duas frases no máximo da resposta total.
    """
    try:
        logging.debug("Enviando prompt para ChatGPT: %s", prompt)
        response = client.responses.create(
            model="gpt-4o",
            instructions="Você é um analista de estatísticas de CS, conciso, sarcástico e provocador.",
            input=prompt
        )
        answer = response.output_text.strip()
        logging.debug("Resposta do ChatGPT: %s", answer)
    except Exception as e:
        logging.exception("Erro ao consultar o ChatGPT:")
        await ctx.send("Erro ao consultar o ChatGPT.")
        return

    # Enviar a resposta (dividindo se necessário)
    if len(answer) > 1900:
        for i in range(0, len(answer), 1900):
            await ctx.send(f"```{answer[i:i+1900]}```")
    else:
        await ctx.send(f"```{answer}```")






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


@bot.command(name="alltimeranking")
async def all_time_ranking(ctx):
    """
    !alltimeranking
    Aggregates all available stats across all months for all players and displays leaderboards.
    """
    import json
    from botocore.exceptions import ClientError

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception:
        await ctx.send("Erro ao carregar dados dos membros do S3.")
        return

    stats_list = []
    # Iterate each member to aggregate their all-time stats
    for discord_id_str, info in members_data.items():
        gc_id = info.get("gc")
        nickname = info.get("nickname", "Unknown")
        if not gc_id:
            continue

        # List all stats files for this player
        prefix = f"players/{gc_id}/stats-"
        try:
            list_resp = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix)
            files = list_resp.get("Contents", [])
        except Exception:
            continue

        if not files:
            continue

        # Initialize aggregate counters
        total_matches = total_wins = total_losses = 0
        total_kills = total_deaths = total_first_kills = 0
        sum_adr = sum_hs = sum_matches_for_avg = 0

        for obj in files:
            try:
                stats_data = json.loads(
                    s3.get_object(Bucket=BUCKET_NAME, Key=obj['Key'])["Body"].read().decode("utf-8")
                )
            except ClientError:
                continue
            except Exception:
                continue

            matches = stats_data.get("total_matches", 0)
            total_matches += matches
            total_wins += stats_data.get("total_wins", 0)
            total_losses += stats_data.get("total_losses", 0)
            total_kills += stats_data.get("total_kills", 0)
            total_deaths += stats_data.get("total_deaths", 0)
            total_first_kills += stats_data.get("total_first_kills", 0)
            if matches > 0:
                sum_adr += stats_data.get("ADR", 0) * matches
                sum_hs += stats_data.get("HS_percent", 0) * matches
                sum_matches_for_avg += matches

        if total_matches == 0:
            continue

        # Compute metrics
        win_rate = (total_wins / total_matches * 100)
        kdr = (total_kills / total_deaths) if total_deaths else total_kills
        avg_adr = (sum_adr / sum_matches_for_avg) if sum_matches_for_avg else 0
        avg_hs = (sum_hs / sum_matches_for_avg) if sum_matches_for_avg else 0
        avg_fk = (total_first_kills / total_matches) if total_matches else 0

        stats_list.append({
            "nickname": nickname,
            "matches": total_matches,
            "win_rate": win_rate,
            "kdr": kdr,
            "adr": avg_adr,
            "hs": avg_hs,
            "avg_fk": avg_fk
        })

    if not stats_list:
        await ctx.send("Nenhum dado de stats encontrado para ranking.")
        return

    # Helper to build ranking text
    def build_ranking(sorted_list, key, label):
        return "\n".join([
            f"{i+1}. {p['nickname']} - {label}: {p[key]:.2f} ({p['matches']} partidas)"
            for i, p in enumerate(sorted_list)
        ])

    # Sort and build each leaderboard
    kdr_sorted = sorted(stats_list, key=lambda x: x['kdr'], reverse=True)
    adr_sorted = sorted(stats_list, key=lambda x: x['adr'], reverse=True)
    fk_sorted = sorted(stats_list, key=lambda x: x['avg_fk'], reverse=True)
    win_sorted = sorted(stats_list, key=lambda x: x['win_rate'], reverse=True)

    embed = discord.Embed(
        title="All Time Ranking",
        description="Leaderboards agregados de todos os meses",
        color=0x3498db
    )
    embed.add_field(name="KDR Ranking", value=f"```{build_ranking(kdr_sorted, 'kdr', 'KDR')}```", inline=False)
    embed.add_field(name="ADR Ranking", value=f"```{build_ranking(adr_sorted, 'adr', 'ADR')}```", inline=False)
    embed.add_field(name="Avg FK Ranking", value=f"```{build_ranking(fk_sorted, 'avg_fk', 'Avg FK')}```", inline=False)
    embed.add_field(name="Win Rate Ranking", value=f"```{build_ranking(win_sorted, 'win_rate', 'Win Rate')}```", inline=False)

    await ctx.send(embed=embed)

@bot.command(name="ranking")
async def ranking(ctx, *, args: str = None):
    await ranking_handler.handle(ctx, args)

# @bot.command(name="ranking2")
# async def ranking(ctx, month: str = None):
#     """
#     !ranking
#     Displays a ranking of members (from members.json stored on S3) for the current month,
#     based on overall KDR, ADR, average first kills per match, and overall win rate.
#     Each ranking shows the member's nickname, metric value, and total matches played.
#     """
#     import json
#     from datetime import datetime
#     from botocore.exceptions import ClientError

#     # Load members.json from S3
#     try:
#         response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
#         members_contents = response["Body"].read().decode("utf-8")
#         members_data = json.loads(members_contents)
#     except Exception as e:
#         await ctx.send("Error loading members data from S3.")
#         return

#     if month:
#         try:
#             datetime.strptime(month, "%Y-%m")
#             month_year = month
#         except ValueError:
#             await ctx.send("Use YYYY-MM format, e.g. `!ranking 2025-04`")
#             return
#     else:
#         month_year = datetime.now().strftime("%Y-%m")
#     stats_list = []

#     # Iterate over each member in members.json
#     for discord_id, info in members_data.items():
#         gc_id = info.get("gc")
#         if not gc_id:
#             continue
#         stats_key = f"players/{gc_id}/stats-{month_year}.json"
#         try:
#             stats_response = s3.get_object(Bucket=BUCKET_NAME, Key=stats_key)
#             stats_contents = stats_response["Body"].read().decode("utf-8")
#             stats = json.loads(stats_contents)
#         except ClientError:
#             continue  # Skip members with no stats file
#         except Exception:
#             continue
        
#         # Extract overall metrics
#         kdr = stats.get("KDR", 0)
#         adr = stats.get("ADR", 0)
#         avg_first = stats.get("average_first_kills_per_match", 0)
#         win_rate = stats.get("overall_win_rate", 0)
#         total_matches = stats.get("total_matches", 0)
#         nickname = info.get("nickname", "Unknown")
        
#         stats_list.append({
#             "discord_id": discord_id,
#             "nickname": nickname,
#             "kdr": kdr,
#             "adr": adr,
#             "avg_first": avg_first,
#             "win_rate": win_rate,
#             "matches": total_matches
#         })
    
#     if not stats_list:
#         await ctx.send("No aggregated stats found for this month.")
#         return

#     # Helper: Build ranking string from a sorted list
#     def build_ranking_str(sorted_list, metric_key, metric_name):
#         lines = []
#         for idx, stat in enumerate(sorted_list, start=1):
#             value = stat[metric_key]
#             lines.append(f"{idx}. {stat['nickname']} - {metric_name}: {value:.2f} ({stat['matches']} matches)")
#         return "\n".join(lines)

#     # Sort members by each metric (descending: higher is better)
#     kdr_sorted = sorted(stats_list, key=lambda x: x["kdr"], reverse=True)
#     adr_sorted = sorted(stats_list, key=lambda x: x["adr"], reverse=True)
#     first_sorted = sorted(stats_list, key=lambda x: x["avg_first"], reverse=True)
#     win_rate_sorted = sorted(stats_list, key=lambda x: x["win_rate"], reverse=True)

#     ranking_kdr = build_ranking_str(kdr_sorted, "kdr", "KDR")
#     ranking_adr = build_ranking_str(adr_sorted, "adr", "ADR")
#     ranking_first = build_ranking_str(first_sorted, "avg_first", "Avg First Kills")
#     ranking_win = build_ranking_str(win_rate_sorted, "win_rate", "Win Rate")

#     embed = discord.Embed(
#         title=f"Member Rankings for {month_year}",
#         description="Rankings based on overall KDR, ADR, Average First Kills per Match, and Win Rate.",
#         color=0x3498db
#     )
#     embed.add_field(name="KDR Ranking", value=f"```{ranking_kdr}```", inline=False)
#     embed.add_field(name="ADR Ranking", value=f"```{ranking_adr}```", inline=False)
#     embed.add_field(name="Avg First Kills Ranking", value=f"```{ranking_first}```", inline=False)
#     embed.add_field(name="Win Rate Ranking", value=f"```{ranking_win}```", inline=False)
    
#     await ctx.send(embed=embed)

@bot.command(name="arca")
async def arca(ctx, month: str = None):
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
    
    all_flag = (month == "-all")

    if month and not all_flag:
        try:
            datetime.strptime(month, "%Y-%m")
            month_year = month
        except ValueError:
            await ctx.send("Use YYYY-MM format, e.g. `!ranking 2025-04`")
            return
    else:
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
        if not all_flag:
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

    if all_flag:
        time_msg = "All time stats"
    else:
        time_msg = month_year

    embed = Embed(
        title=f"Group (Arca) Performance on Each Map ({time_msg})",
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

@bot.command(name="LKS")
async def lks_command(ctx):
    """
    !LKS
    Lista imagens do folder 'lks' no S3, envia elas no Discord e pede ao GPT-4o para julgar
    zapg0d e doctor (LKS o iron burro) com base no conteúdo visual e nos nomes dos arquivos.
    """
    from botocore.exceptions import ClientError
    import base64
    import requests

    await ctx.send("🔍 Carregando imagens do LKS e preparando a análise do ZapIA insano...")

    # Lista os objetos no prefixo 'lks/'
    try:
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="lks/")
        contents = response.get("Contents", [])
        if not contents:
            await ctx.send("❌ Nenhuma imagem encontrada no folder 'lks/'.")
            return
    except ClientError as e:
        await ctx.send("❌ Erro ao listar o folder 'lks/' no S3.")
        return

    # Filtra imagens válidas
    image_keys = [obj["Key"] for obj in contents if obj["Key"].lower().endswith(('.png', '.jpg', '.jpeg', '.gif'))]
    if not image_keys:
        await ctx.send("❌ Nenhuma imagem válida encontrada no folder 'lks/'.")
        return

    multimodal_inputs = []
    signed_urls = []

    # Helper para converter imagem S3 em data URL base64
    def s3_image_to_base64(signed_url):
        try:
            response = requests.get(signed_url)
            response.raise_for_status()
            content_type = response.headers['Content-Type']
            base64_data = base64.b64encode(response.content).decode('utf-8')
            return f"data:{content_type};base64,{base64_data}"
        except Exception as e:
            logging.exception("Erro ao converter imagem para base64:")
            return None

    # Envia as imagens no Discord e prepara para o GPT
    for key in image_keys:
        try:
            signed_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': BUCKET_NAME, 'Key': key},
                ExpiresIn=3600  # válido por 1h
            )
            signed_urls.append(signed_url)

            # Enviar no Discord
            embed = discord.Embed(title=f"Imagem: {key.split('/')[-1]}")
            embed.set_image(url=signed_url)
            await ctx.send(embed=embed)

            # Converte para base64 e adiciona ao multimodal
            base64_url = s3_image_to_base64(signed_url)
            if base64_url:
                multimodal_inputs.append({
                    "type": "image_url",
                    "image_url": {"url": base64_url}
                })
            else:
                await ctx.send(f"⚠️ Erro ao processar imagem `{key.split('/')[-1]}` para o ZapIA.")
        except Exception as e:
            logging.exception(f"Erro ao gerar signed URL para {key}:")
            await ctx.send(f"⚠️ Erro ao enviar imagem `{key.split('/')[-1]}`")

    if not multimodal_inputs:
        await ctx.send("❌ Nenhuma imagem pôde ser processada para o ZapIA.")
        return

    # Adiciona o prompt textual
    multimodal_inputs.append({
        "type": "text",
        "text": """
Você é o ZapIA, um analista de CS e roaster de perfis. As imagens anexadas são resultados de partidas e fotos do player doctor, conhecido como LKS (o iron burro). Analise e dê sua opinião com sarcasmo, ofensas criativas e comparações com outros players. Seja curto e direto.
"""
    })

    # Envia para o GPT-4o multimodal
    try:
        logging.debug("Enviando conteúdo multimodal para ChatGPT (LKS)")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Você é um analista de CS e de imagens, sarcástico, ofensivo e provocador."},
                {"role": "user", "content": multimodal_inputs}
            ]
        )
        answer = response.choices[0].message.content.strip()
        logging.debug("Resposta do ChatGPT (LKS multimodal): %s", answer)
    except Exception as e:
        logging.exception("❌ Erro ao consultar o ChatGPT para !LKS:")
        await ctx.send("❌ Erro ao consultar o ChatGPT multimodal para o comando !LKS.")
        return

    # Envia a resposta no Discord
    if len(answer) > 1900:
        await ctx.send("🧠 **ZapIA disse:**")
        for i in range(0, len(answer), 1900):
            await ctx.send(f"```{answer[i:i+1900]}```")
    else:
        await ctx.send(f"🧠 **ZapIA disse:**\n```{answer}```")



@bot.command(name="ranking_mix2")
async def ranking_mix(ctx, period: str = None):
    """
    !ranking_mix [YYYY-MM | -all]
    Generates leaderboards for mix matches where both teams have at least one group player.
    If period is '-all', aggregates stats from all time; otherwise for the specified month.
    """
    import json
    from datetime import datetime
    from botocore.exceptions import ClientError

    # Load members.json from S3
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=OBJECT_KEY)
        members_contents = response["Body"].read().decode("utf-8")
        members_data = json.loads(members_contents)
    except Exception:
        await ctx.send("Error loading members data from S3.")
        return

    # Build mappings: discord_id_str -> gc_id and gc_id -> nickname
    discord_to_gc = {did: str(info.get("gc")) for did, info in members_data.items() if info.get("gc")}
    gc_to_nickname = {str(info.get("gc")): info.get("nickname", f"Unknown({info.get('gc')})")
                      for info in members_data.values() if info.get("gc")}
    if not discord_to_gc:
        await ctx.send("No group GC ids found in members data.")
        return

    # Determine period: month or all-time
    all_flag = (period == "-all")
    if period and not all_flag:
        try:
            datetime.strptime(period, "%Y-%m")
            month_year = period
        except ValueError:
            await ctx.send("Use YYYY-MM format or '-all' for all time, e.g. `!ranking_mix 2025-04` or `!ranking_mix -all`.")
            return
    else:
        month_year = datetime.now().strftime("%Y-%m")

    # List match files from S3
    try:
        objects = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix="matches/")
        files = objects.get("Contents", [])
    except Exception:
        await ctx.send("Error listing match objects from S3.")
        return

    mix_stats = {}
    counted_matches = set()

    # Iterate through matches
    for obj in files:
        key = obj["Key"]
        try:
            match_data = json.loads(
                s3.get_object(Bucket=BUCKET_NAME, Key=key)["Body"].read().decode("utf-8")
            )
        except Exception:
            continue

        # Filter by month unless all-time
        if not all_flag:
            date_str = match_data.get("data")  # format "dd/mm/YYYY HH:MM"
            if not date_str:
                continue
            try:
                match_date = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            except Exception:
                continue
            if match_date.strftime("%Y-%m") != month_year:
                continue

        # Ensure each match counted once
        match_id = match_data.get("id") or match_data.get("match_id") or key.split("/")[-1].split(".")[0]
        if match_id in counted_matches:
            continue
        counted_matches.add(match_id)

        jogos = match_data.get("jogos", {})
        players_data = jogos.get("players", {})
        try:
            score_a = int(jogos.get("score_a", 0))
            score_b = int(jogos.get("score_b", 0))
        except Exception:
            score_a, score_b = 0, 0
        winning_team = "team_a" if score_a > score_b else "team_b" if score_b > score_a else None

        # Identify group players in each team
        team_a_group = [p for p in players_data.get("team_a", [])
                        if str(p.get("idplayer")) in discord_to_gc.values()]
        team_b_group = [p for p in players_data.get("team_b", [])
                        if str(p.get("idplayer")) in discord_to_gc.values()]
        if not team_a_group or not team_b_group:
            continue

        # Initialize stats for a GC id
        def ensure(gc):
            if gc not in mix_stats:
                mix_stats[gc] = {"kills":0, "deaths":0, "damage":0, "rounds":0,
                                 "first_kills":0, "wins":0, "matches":0}

        # Accumulate for team A
        for p in team_a_group:
            gc = str(p.get("idplayer"))
            ensure(gc)
            st = mix_stats[gc]
            st["matches"] += 1
            st["kills"] += int(p.get("nb_kill", 0))
            st["deaths"] += int(p.get("death", 0))
            st["damage"] += int(p.get("damage", 0))
            st["rounds"] += int(p.get("rounds_played", 0))
            st["first_kills"] += int(p.get("firstkill", 0))
            if winning_team == "team_a":
                st["wins"] += 1

        # Accumulate for team B
        for p in team_b_group:
            gc = str(p.get("idplayer"))
            ensure(gc)
            st = mix_stats[gc]
            st["matches"] += 1
            st["kills"] += int(p.get("nb_kill", 0))
            st["deaths"] += int(p.get("death", 0))
            st["damage"] += int(p.get("damage", 0))
            st["rounds"] += int(p.get("rounds_played", 0))
            st["first_kills"] += int(p.get("firstkill", 0))
            if winning_team == "team_b":
                st["wins"] += 1

    if not mix_stats:
        await ctx.send("No mix matches found for the specified period.")
        return

    # Compute metrics and prepare ranking
    players_list = []
    for gc, st in mix_stats.items():
        m = st["matches"]
        kdr = st["kills"] / st["deaths"] if st["deaths"] else st["kills"]
        adr = st["damage"] / st["rounds"] if st["rounds"] else 0
        avg_fk = st["first_kills"] / m if m else 0
        win_rate = (st["wins"] / m * 100) if m else 0
        nickname = gc_to_nickname.get(gc, f"Unknown({gc})")
        players_list.append({"nickname": nickname, "kdr": kdr, "adr": adr,
                             "avg_fk": avg_fk, "win_rate": win_rate, "matches": m})

    # Helper to build ranking string
    def build(sorted_list, key, label):
        return "\n".join(
            f"{i+1}. {p['nickname']} - {label}: {p[key]:.2f} ({p['matches']} matches)"
            for i, p in enumerate(sorted_list)
        )

    kdr_sorted = sorted(players_list, key=lambda x: x["kdr"], reverse=True)
    adr_sorted = sorted(players_list, key=lambda x: x["adr"], reverse=True)
    fk_sorted = sorted(players_list, key=lambda x: x["avg_fk"], reverse=True)
    win_sorted = sorted(players_list, key=lambda x: x["win_rate"], reverse=True)

    title = f"Mix Ranking {'All Time' if all_flag else month_year}"
    embed = discord.Embed(title=title, description="Mix matches stats", color=0x9b59b6)
    embed.add_field(name="KDR Ranking", value=f"```{build(kdr_sorted, 'kdr', 'KDR')}```", inline=False)
    embed.add_field(name="ADR Ranking", value=f"```{build(adr_sorted, 'adr', 'ADR')}```", inline=False)
    embed.add_field(name="Avg First Kills Ranking", value=f"```{build(fk_sorted, 'avg_fk', 'Avg FK')}```", inline=False)
    embed.add_field(name="Win Rate Ranking", value=f"```{build(win_sorted, 'win_rate', 'Win Rate')}```", inline=False)
    await ctx.send(embed=embed)







@bot.command(name="ranking_mix")
async def ranking_mix(ctx, *, args: str = None):
    await ranking_mix_handler.handle(ctx, args)




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
    with open("config.json", "r") as config_file:
        config = json.load(config_file)

    TOKEN = config["discord_token"]
    OPENAI_API_KEY = config["openai_api_key"]
    client = OpenAI(
    # This is the default and can be omitted
    api_key=OPENAI_API_KEY,
    )
    bot.run(TOKEN)
