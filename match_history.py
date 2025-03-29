# match_history.py
import os
import requests
import time
import random
import json
from datetime import datetime

def get_match_history(gc_id, month_year):
    """
    Fetches match history for a given GC id and month (YYYY-MM).
    Saves the history to /players/{gc_id}/{gc_id}-{month_year}-history.json
    and returns the full file path.
    """
    file_name = f"{gc_id}-{month_year}-history.json"
    players_folder = os.path.join("players", str(gc_id))
    os.makedirs(players_folder, exist_ok=True)
    file_path = os.path.join(players_folder, file_name)

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "authorization": "Basic ZnJvbnRlbmQ6NDdhMTZHMmtHTCFmNiRMRUQlJVpDI25X",
        "priority": "u=1, i",
        "referer": f"https://gamersclub.com.br/player/{gc_id}",
        "sec-ch-ua": '"Chromium";v="134", "Not:A-Brand";v="24", "Google Chrome";v="134"',
        "sec-ch-ua-arch": '"arm"',
        "sec-ch-ua-bitness": '"64"',
        "sec-ch-ua-full-version": '"134.0.6998.45"',
        "sec-ch-ua-full-version-list": '"Chromium";v="134.0.6998.45", "Not:A-Brand";v="24.0.0.0", "Google Chrome";v="134.0.6998.45"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": '""',
        "sec-ch-ua-platform": '"macOS"',
        "sec-ch-ua-platform-version": '"14.7.1"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "Cookie": "gclubsess=6de293ceadbd014c40c4c7c84b34a8b53b5f16d7"
    }

    page = 0
    results = []
    while True:
        url = f"https://gamersclub.com.br/api/box/historyMatchesPage/{gc_id}/{month_year}/{page}"
        print(f"Fetching match history for GC {gc_id}, page {page}...")
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            break
        data = response.json()
        matches = data.get("monthMatches", [])
        if not matches:
            print("No more matches found.")
            break
        for match in matches:
            match_id = match.get("id")
            match_map = match.get("map")
            win_status = match.get("win")
            results.append({
                "match_id": match_id,
                "map": match_map,
                "win": win_status
            })
            print(f"Added match {match_id} ({match_map}) win: {win_status}")
        page += 1
        time.sleep(random.uniform(1, 2))

    with open(file_path, "w") as f:
        json.dump(results, f, indent=4)
    print(f"Match history for GC {gc_id} saved to {file_path}")
    return file_path
