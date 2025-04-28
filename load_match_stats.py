import os
import json
import time
import cloudscraper

# ——————————————
# CONFIGURATION
# ——————————————

# 1) Point this at the JSON you pasted
COOKIES_FILE = "cookies.json"

# 2) How many retries & back-off multiplier
MAX_RETRIES    = 3
BACKOFF_FACTOR = 1.0
TIMEOUT        = 15

# 3) Static headers (you can trim these down if you like)
HEADERS = {
    "accept":          "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
    "referer":         "https://gamersclub.com.br/lobby/match/",
    "user-agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/134.0.0.0 Safari/537.36",
}


def load_cookies():
    """Read your exported cookies JSON and return a dict for requests."""
    if not os.path.exists(COOKIES_FILE):
        raise FileNotFoundError(f"{COOKIES_FILE} not found")
    with open(COOKIES_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    # build name→value map
    return {c["name"]: c["value"] for c in raw}


def load_match_stats(history_file: str):
    """
    For each match_id in history_file, fetch its stats via cloudscraper,
    sending your full cookie jar, retrying on 5xx with exponential back-off.
    """
    if not os.path.exists(history_file):
        print(f"[!] History file not found: {history_file}")
        return

    # load history
    with open(history_file, encoding="utf-8") as f:
        try:
            match_history = json.load(f)
        except Exception as e:
            print("[!] Error parsing history JSON:", e)
            return

    # prepare output folder
    stats_dir = os.path.join(os.getcwd(), "matches")
    os.makedirs(stats_dir, exist_ok=True)

    # set up scraper + cookies
    scraper = cloudscraper.create_scraper()
    cookies = load_cookies()
    base_url = "https://gamersclub.com.br/lobby/match/{match_id}/1"

    for match in match_history:
        match_id = match.get("match_id")
        if not match_id:
            print("[!] Skipping entry with no match_id:", match)
            continue

        out_file = os.path.join(stats_dir, f"{match_id}.json")
        if os.path.exists(out_file):
            print(f"[{match_id}] already downloaded, skipping.")
            continue

        print(f"[{match_id}] processing…")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"  → attempt {attempt}/{MAX_RETRIES}")
                resp = scraper.get(
                    base_url.format(match_id=match_id),
                    headers=HEADERS,
                    cookies=cookies,
                    timeout=TIMEOUT
                )
            except Exception as e:
                print(f"    network error: {e}")
            else:
                code = resp.status_code
                print(f"    status {code}")
                if code == 200:
                    try:
                        data = resp.json()
                    except Exception as e:
                        print(f"    JSON decode error: {e}")
                        break
                    with open(out_file, "w", encoding="utf-8") as wf:
                        json.dump(data, wf, indent=4, ensure_ascii=False)
                    print(f"    ✅ saved to {out_file}")
                    break

                if 500 <= code < 600:
                    backoff = BACKOFF_FACTOR * (2 ** (attempt - 1))
                    print(f"    server error, sleeping {backoff}s")
                    time.sleep(backoff)
                    continue

                # any other status: stop retrying
                print(f"    non-retryable status {code}, skipping.")
                break
        else:
            # ran all attempts without break
            print(f"    ❌ failed after {MAX_RETRIES} attempts")

    print("Finished processing all matches.")
