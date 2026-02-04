from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
import discord
from discord.ext import commands

from .levels import LevelService
from .storage import LocalMembersStore
from .cogs.admin import AdminCog
from .cogs.mix import MixCog
from .cogs.rankings import RankingsCog
from .cogs.stats import StatsCog


log = logging.getLogger(__name__)


DEFAULT_BOT_ADMINS: List[int] = [
    291617683416285194,
    701661704844738580,
]


class ZapBot(commands.Bot):
    def __init__(self, *, levels: LevelService, bot_admins: List[int]):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.levels = levels
        self.bot_admins = bot_admins

    async def setup_hook(self) -> None:
        # discord.py 2.x: add_cog is async
        await self.add_cog(MixCog(self, levels=self.levels, bot_admins=self.bot_admins))
        await self.add_cog(AdminCog(self, levels=self.levels, bot_admins=self.bot_admins))
        await self.add_cog(StatsCog(self, members_path="members.json"))
        await self.add_cog(RankingsCog(self, levels=self.levels, members_path="members.json"))


def create_bot(bot_admins: List[int] | None = None) -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.voice_states = True

    store = LocalMembersStore("members.json")
    levels = LevelService(store=store)
    admins = bot_admins or DEFAULT_BOT_ADMINS

    bot: commands.Bot = ZapBot(levels=levels, bot_admins=admins)

    @bot.command(name="help")
    async def help_command(ctx: commands.Context):
        help_text = (
            "**Comandos do Zap Bot (local)**\n\n"
            "__👥 Gestão de Times__\n"
            "**!mix [<n>] [--exclude/-e @User …] [--extra/-x @User …] [--duelo/-t @A @B]**\n"
            "**!arere** – Divide o canal de voz aleatoriamente em dois times.\n"
            "**!simulatemix** – Simula um mix com 10 jogadores do `members.json`.\n\n"
            "__📊 Estatísticas__\n"
            "**!stats @Player [YYYY-MM]** – Lê `players/<gc>/stats-YYYY-MM.json`.\n"
            "**!alltimestats @Player** – Agrega todos `players/<gc>/stats-*.json`.\n"
            "**!ranking [YYYY-MM | -all] [--no-mix]** – Rankings do grupo (local).\n"
            "**!ranking_mix [YYYY-MM | -all] [-last N]** – Ranking só de mixes (local).\n"
            "**!ranking_creators [YYYY-MM | -all]** – Ranking criadores de lobby (local).\n"
            "**!arca [YYYY-MM | -all]** – Performance do grupo por mapa (local).\n"
            "**!c4** – Ranking C4 plantada (local).\n"
            "**!meu_vintao** – Stats locais do LKS (ranked pro/qualify).\n\n"
            "__🔧 Administração (Bot Admins)__\n"
            "**!setlevel @User <level>** – Salva nível no `members.json`.\n"
            "**!addtemp @User <level>** – Nível temporário (memória).\n"
            "**!clear** – Limpa mensagens do canal.\n"
            "**!players** – Lista players e níveis.\n"
            "**!botadmins** – Lista admins.\n\n"
            "_Obs: Projeto roda 100% local (sem integrações cloud)._"
        )
        await ctx.send(help_text)

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id if bot.user else "?")

    return bot


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # On Windows, PowerShell commonly writes UTF-8 with BOM; use utf-8-sig to support that.
    # Also resolve .env relative to repo root so running from other working dirs still works.
    repo_root = Path(__file__).resolve().parent.parent
    dotenv_path = repo_root / ".env"
    load_dotenv(dotenv_path=dotenv_path, encoding="utf-8-sig")

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise SystemExit(f"DISCORD_TOKEN não encontrado. Verifique o arquivo: {dotenv_path}")

    bot = create_bot()
    bot.run(token)


