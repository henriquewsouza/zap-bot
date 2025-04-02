import os
import cloudscraper
import json

def fetch_match_stats(match_id):
    # Ensure the "matches" folder exists
    os.makedirs("matches", exist_ok=True)
    
    # Save the file as matches/<match_id>.json
    local_filename = os.path.join("matches", f"{match_id}.json")

    url = f"https://gamersclub.com.br/lobby/match/{match_id}/1"
    headers = {
        "accept": "application/json, text/javascript, */*; q=0.01",
        "accept-language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "priority": "u=1, i",
        "referer": f"https://gamersclub.com.br/lobby/match/{match_id}",
        "sec-ch-ua": "\"Chromium\";v=\"134\", \"Not:A-Brand\";v=\"24\", \"Google Chrome\";v=\"134\"",
        "sec-ch-ua-arch": "\"arm\"",
        "sec-ch-ua-bitness": "\"64\"",
        "sec-ch-ua-full-version": "\"134.0.6998.45\"",
        "sec-ch-ua-full-version-list": "\"Chromium\";v=\"134.0.6998.45\", \"Not:A-Brand\";v=\"24.0.0.0\", \"Google Chrome\";v=\"134.0.6998.45\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-model": "\"\"",
        "sec-ch-ua-platform": "\"macOS\"",
        "sec-ch-ua-platform-version": "\"14.7.1\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "Cookie": "gclubsess=6de293ceadbd014c40c4c7c84b34a8b53b5f16d7"
    }

    print(f"Fetching stats for match {match_id} using cloudscraper...")
    scraper = cloudscraper.create_scraper()
    try:
        response = scraper.get(url, headers=headers, timeout=15)
    except Exception as e:
        print("Error during scraper.get:", e)
        return None

    print("Response status code:", response.status_code)
    print("Response content (first 500 chars):", response.text[:500])
    if response.status_code != 200:
        print(f"Error fetching match {match_id}: {response.status_code}")
        return None

    try:
        match_data = response.json()
    except Exception as e:
        print("Error decoding JSON:", e)
        return None

    json_data = json.dumps(match_data, indent=4)
    try:
        with open(local_filename, "w", encoding="utf-8") as f:
            f.write(json_data)
        print(f"Saved stats for match {match_id} to local file: {local_filename}")
    except Exception as e:
        print("Error saving file:", e)
        return None

    return local_filename

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python get_single_match_stats.py <match_id>")
        sys.exit(1)
    match_id = sys.argv[1]
    fetch_match_stats(match_id)
