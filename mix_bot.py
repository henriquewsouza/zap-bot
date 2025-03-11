import os
import getpass  # Securely prompt for the token without echoing it
import discord
from discord.ext import commands
import itertools
import json
import asyncio

# Constants
TIMES_CHANNEL_ID = 1335633874453008414
BOT_ADMINS = [291617683416285194, 701661704844738580]
MEMBERS_FILE = "members.json"


# Load user levels from file.
def load_user_levels():
    with open(MEMBERS_FILE, "r", encoding="utf-8") as f:
        user_data = json.load(f)
    return {int(user_id): info for user_id, info in user_data.items()}

# Check if a context author is a bot admin.
def is_bot_admin(ctx):
    return ctx.author.id in BOT_ADMINS

# Set up Discord bot with proper intents.
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# Global flag to prevent concurrent mixes.
mix_in_progress = False

# --- Team Building Helpers ---

def build_team_message(team1, team2):
    """
    Construct a message showing both teams sorted by level (highest first),
    along with total team skill and the skill difference.
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
        f"**Difference:** {abs(total_team1 - total_team2)}"
    )
    return message

def is_valid_partition(team1, team2, zapgod_id=291617683416285194, jotalha_id=692595982378074222):
    """
    Return True if Zapgod and JOTALHA are not on the same team.
    """
    if (any(m.id == zapgod_id for m in team1) and any(m.id == jotalha_id for m in team1)) or \
       (any(m.id == zapgod_id for m in team2) and any(m.id == jotalha_id for m in team2)):
        return False
    return True

def generate_valid_partitions(members):
    """
    Generate all valid team partitions (teams of 5) that satisfy the
    Zapgod/JOTALHA constraint.
    Returns a list of tuples: (difference, team1, team2).
    """
    partitions = []
    for team1 in itertools.combinations(members, 5):
        team2 = [member for member in members if member not in team1]
        if not is_valid_partition(team1, team2):
            continue
        total_team1 = sum(user_levels[m.id]["level"] for m in team1)
        total_team2 = sum(user_levels[m.id]["level"] for m in team2)
        diff = abs(total_team1 - total_team2)
        partitions.append((diff, team1, team2))
    return partitions

def select_best_partition(partitions):
    """
    Sort the partitions by the difference in total skill and return the best one.
    """
    partitions.sort(key=lambda x: x[0])
    return partitions[0]

async def send_mix_result(channel, team1, team2):
    """
    Send the generated team partition result to the specified channel.
    """
    message = build_team_message(team1, team2)
    await channel.send("**Teams Generated:**\n" + message)

# --- Parsing Helpers for Mix Command ---

async def parse_mix_args(ctx):
    """
    Parse the command arguments from ctx.message.content.
    The expected format is:
      !mix [--exclude or -e] <member mentions> [--extra or -x] <member mentions>
    If no flag is set, defaults to extras.
    Returns a tuple: (exclusions, extras) as lists of discord.Member.
    """
    args = ctx.message.content.split()[1:]  # skip the command name
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
            # Default to extras if no mode is set.
            if mode is None:
                mode = "extra"
            if mode == "exclude":
                exclusions.append(member)
            elif mode == "extra":
                extras.append(member)
    return exclusions, extras

def get_mix_members(ctx, exclusions, extras):
    """
    Build the final list of members for the mix.
    
    Start with non-bot members from the voice channel (if any), remove any in the exclusions list,
    then add the extra members (avoiding duplicates).
    """
    members = []
    if ctx.author.voice is not None:
        voice_members = [member for member in ctx.author.voice.channel.members if not member.bot]
        members.extend(voice_members)
    # Remove excluded members
    exclusions_ids = {member.id for member in exclusions}
    members = [m for m in members if m.id not in exclusions_ids]
    # Add extras (if not already present)
    for member in extras:
        if all(member.id != m.id for m in members):
            members.append(member)
    return members

# --- Bot Commands ---

@bot.command(name="mix2")
async def mix_teams(ctx):
    """
    !mix [--exclude @User ...] [--extra @User ...]

    Generates two balanced teams from exactly 10 non-bot members combined from:
      - Members in your current voice channel (after removing those specified by --exclude), and 
      - Any extra members specified by --extra (even if they aren’t in the voice channel).

    The final pool must total exactly 10 members. The best valid partition (respecting the Zapgod/JOTALHA constraint)
    is sent immediately.
    """
    global mix_in_progress
    if mix_in_progress:
        await ctx.send("A team mix is already in progress. Please wait until it is finished.")
        return

    mix_in_progress = True
    try:
        times_channel = bot.get_channel(TIMES_CHANNEL_ID)
        if not times_channel:
            await ctx.send(f"Error: Unable to find the #times channel (ID {TIMES_CHANNEL_ID}).")
            return

        exclusions, extras = await parse_mix_args(ctx)
        members = get_mix_members(ctx, exclusions, extras)
        if len(members) != 10:
            await times_channel.send("There must be exactly 10 members (voice channel members minus exclusions plus extras) to start a mix.")
            return

        partitions = generate_valid_partitions(members)
        if not partitions:
            await times_channel.send("No valid team partitions available with the current constraints.")
            return

        diff, team1, team2 = select_best_partition(partitions)
        await send_mix_result(times_channel, team1, team2)
    finally:
        mix_in_progress = False

@bot.command(name="clear")
@commands.check(is_bot_admin)
@commands.has_permissions(manage_messages=True)
async def clear(ctx):
    """
    !clear

    Clears all (non-pinned) messages from the #times channel.
    (Requires Manage Messages permission; Bot Admins only.)
    """
    times_channel = bot.get_channel(TIMES_CHANNEL_ID)
    if not times_channel:
        await ctx.send(f"Error: Unable to find the #times channel (ID {TIMES_CHANNEL_ID}).")
        return

    deleted = await times_channel.purge(limit=None)
    confirmation = await times_channel.send(f"Cleared {len(deleted)} messages from this channel.")
    await asyncio.sleep(5)
    await confirmation.delete()

@bot.command(name="setlevel2")
@commands.check(is_bot_admin)
async def set_level(ctx, member: discord.Member, level: int):
    """
    !setlevel @User <level>

    Permanently updates a member's level.
    Updates the in-memory user_levels data and writes the change to members.json.
    (Bot Admins only.)
    """
    global user_levels
    user_levels[member.id] = {
        "level": level,
        "nickname": member.display_name
    }
    with open(MEMBERS_FILE, "w", encoding="utf-8") as f:
        json.dump({str(uid): info for uid, info in user_levels.items()}, f, indent=4)
    await ctx.send(f"Updated {member.mention}'s level to {level}.")

@bot.command(name="addtemp2")
@commands.check(is_bot_admin)
async def add_temp(ctx, member: discord.Member, level: int):
    """
    !addtemp @User <level>

    Adds a temporary level for a member (in-memory only).
    If the member is already in the list, advises using !setlevel.
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

@bot.command(name="players2")
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

@bot.command(name="help2")
async def help_command(ctx):
    """
    !help

    Displays the list of available bot commands.
    """
    help_text = (
        "**Bot Commands:**\n"
        "**!mix [--exclude @User ...] [--extra @User ...]**\n"
        "   - Generates two balanced teams from exactly 10 non-bot members. It starts with all voice channel members, \n"
        "     removes those specified after --exclude, and adds those specified after --extra.\n"
        "**!clear**\n"
        "   - Clears all (non-pinned) messages from the #times channel. (Requires Manage Messages permission; Bot Admins only.)\n"
        "**!setlevel @User <level>**\n"
        "   - Permanently updates a member's level and writes the change to members.json. (Bot Admins only.)\n"
        "**!addtemp @User <level>**\n"
        "   - Temporarily adds a member with a given level (in-memory only). (Bot Admins only.)\n"
        "**!players**\n"
        "   - Displays the current list of players along with their levels and nicknames.\n"
        "**!botadmins**\n"
        "   - Displays the current list of BotAdmins along with their levels and nicknames."
    )
    await ctx.send(help_text)

@bot.command(name="botadmins2")
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

# --- Initialization ---
user_levels = load_user_levels()
if __name__ == '__main__':
    TOKEN = getpass.getpass("Enter your Discord token: ")
    bot.run(TOKEN)
