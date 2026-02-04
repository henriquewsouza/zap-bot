# zap-bot (local)

Discord bot + local stats utilities.

## Running the bot (Windows / PowerShell)

```powershell
cd C:\Users\henri\zap-bot
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
Copy-Item env.template .env
notepad .env   # fill DISCORD_TOKEN
py .\mix_bot.py
```

### Required `.env`

- `DISCORD_TOKEN`: your Discord bot token

### Optional `.env` (only for GamersClub download scripts)

- `GAMERSCLUB_ACCESS_TOKEN`
- `GAMERSCLUB_SESSION_COOKIE` (you can paste either the raw value or `gclubsess=<value>`)

## Local data layout

- `members.json`: members metadata + levels (used by the bot)
- `players/<gc_id>/stats-YYYY-MM.json`: aggregated per-player monthly stats
- `matches/*.json`: raw match JSON files


