import os
import getpass  # Securely prompt for the token without echoing it
import discord
from discord.ext import commands
import itertools
import json
import asyncio
import random
import boto3
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
user_levels = load_user_levels()

# ---------------------------
# Discord Bot Setup
# ---------------------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

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
