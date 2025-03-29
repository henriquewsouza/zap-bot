# get_single_match_stats.py
import os
import requests
import json

def fetch_match_stats(match_id):
    """
    Fetches full match stats for the given match id.
    Saves the stats to the 'matches' folder as {match_id}.json.
    If the file exists, skips retrieval.
    Returns the file path (or None on error).
    """
    os.makedirs("matches", exist_ok=True)
    match_file = os.path.join("matches", f"{match_id}.json")
    if os.path.exists(match_file):
        print(f"Stats for match {match_id} already exist. Skipping.")
        return match_file

    url = f"https://gamersclub.com.br/lobby/match/{match_id}/1"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "priority": "u=1, i",
        "referer": f"https://gamersclub.com.br/lobby/match/{match_id}",
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
        "x-requested-with": "XMLHttpRequest",
        "Cookie": "gclubsess=6de293ceadbd014c40c4c7c84b34a8b53b5f16d7"
    }
    print(f"Fetching stats for match {match_id}...")
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Error fetching match {match_id}: {response.status_code}")
        return None
    match_data = response.json()
    with open(match_file, "w") as f:
        json.dump(match_data, f, indent=4)
    print(f"Saved stats for match {match_id} to {match_file}")
    return match_file

if __name__ == "__main__":
    # If run as a script, use command-line argument (not needed when called from another module)
    import sys
    if len(sys.argv) < 2:
        print("Usage: python get_single_match_stats.py <match_id>")
        sys.exit(1)
    match_id = sys.argv[1]
    fetch_match_stats(match_id)
