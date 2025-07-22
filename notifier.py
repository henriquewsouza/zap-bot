# notifier.py
import datetime, aiohttp, discord
from discord.ext import tasks

# ─── AJUDANTES ────────────────────────────────────────────────────────────────
def local_time_to_utc(hour: int, minute: int = 0,
                      tz: datetime.tzinfo = datetime.timezone(
                          datetime.timedelta(hours=-3))) -> datetime.time:
    """
    Converte um horário local fixo (ex.: 8 h em America/Sao_Paulo, UTC‑3) para um
    objeto `datetime.time` marcado em UTC, ideal para usar em tasks.loop(time=…).
    """
    today_local = datetime.datetime.now(tz).replace(hour=hour, minute=minute,
                                                    second=0, microsecond=0)
    today_utc   = today_local.astimezone(datetime.timezone.utc)
    return datetime.time(today_utc.hour, today_utc.minute,
                         tzinfo=datetime.timezone.utc)

# ─── CLASSE PRINCIPAL ─────────────────────────────────────────────────────────
class TeamMatchNotifier:
    """
    Verifica diariamente se um time joga e envia aviso em um canal Discord.

    Por padrão usa TheSportsDB (endpoint eventsday.php) porque é simples e tem
    key pública gratuita (“1”).  Para outros esportes/time basta instanciar de
    novo com parâmetros diferentes.
    """

    def __init__(
        self,
        bot:          discord.Client,
        channel_id:   int,
        team_id:      int,
        team_label:   str,
        check_time:   datetime.time,
        api_key:      str = "123",
        sport:        str = "Soccer",
    ):
        self.bot         = bot
        self._cid        = channel_id
        self._team_id    = str(team_id)
        self._label      = team_label
        self._sport      = sport
        self._api_key    = api_key
        self._check_time = check_time
        self._http       = aiohttp.ClientSession()

        # cria dinamicamente o loop com o horário escolhido
        self._daily_check = tasks.loop(time=check_time)(self._check_and_notify)

    # ─── LOOP / CHECK ─────────────────────────────────────────────────────────
    async def _check_and_notify(self):
        today = datetime.date.today().isoformat()
        url = (f"https://www.thesportsdb.com/api/v1/json/{self._api_key}"
               f"/eventsday.php?d={today}&s={self._sport}")

        async with self._http.get(url) as resp:
            data = await resp.json()

        events = data.get("events") or []
        games_today = [
            ev for ev in events
            if ev.get("idHomeTeam") == self._team_id
            or ev.get("idAwayTeam") == self._team_id
        ]

        if not games_today:  # silêncio se não há partida
            return

        embed = discord.Embed(
            title=f"⚽  Jogo do {self._label} hoje!",
            description="\n".join(
                f"**{ev['strHomeTeam']} x {ev['strAwayTeam']}** — "
                f"{ev['strLeague']} às {ev['strTimeLocal'][:5]}"
                for ev in games_today
            ),
            colour=0x3498db,
        )
        channel = self.bot.get_channel(self._cid)
        if channel:
            await channel.send(embed=embed)

    # ─── CONTROLES EXTERNOS ───────────────────────────────────────────────────
    def start(self):
        """Inicia o loop; chame depois que o bot estiver online."""
        if not self._daily_check.is_running():
            self._daily_check.start()

    async def close(self):
        """Fecha sessão HTTP; opcional num shutdown limpo."""
        await self._http.close()
