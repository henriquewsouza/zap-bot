#!/usr/bin/env python3
# fetch_rpro_stats.py (versão com pré‑cheque de arquivos)

import os, sys, json, time, random, requests, cloudscraper
from typing import Dict, List, Optional

# ── CONFIG ────────────────────────────────────────────────────────────────
COOKIES_FILE = "cookies.json"
HISTORY_DIR  = "ranked_pro_matches"    # históricos mensais
STATS_DIR    = "match_stats"           # destino para stats

TIMEOUT        = 20
MAX_RETRIES    = 3
BACKOFF_FACTOR = 1.5

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/138.0.0.0 Safari/537.36"),
    "x-requested-with": "XMLHttpRequest",
}
# ──────────────────────────────────────────────────────────────────────────


def load_cookies(path: str) -> Dict[str, str]:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {c["name"]: c["value"] for c in raw}


def history_files(gc_id: int) -> List[str]:
    folder = os.path.join(HISTORY_DIR, str(gc_id))
    return sorted(os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".json"))


def match_ids(path: str) -> List[int]:
    with open(path, encoding="utf-8") as f:
        return [m["id"] for m in json.load(f) if "id" in m]


def make_scraper(cookies: Dict[str, str]) -> cloudscraper.CloudScraper:
    s = cloudscraper.create_scraper()
    s.headers.update(HEADERS)
    s.headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    return s


def fetch_stats(s: cloudscraper.CloudScraper, mid: int) -> Optional[dict]:
    url = f"https://gamersclub.com.br/lobby/match/{mid}/1"
    ref = {"referer": f"https://gamersclub.com.br/lobby/match/{mid}"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = s.get(url, headers=ref, timeout=TIMEOUT)
        except requests.RequestException as e:
            print(f"      rede: {e}")
            continue

        if r.status_code == 200:
            try:
                return r.json()
            except json.JSONDecodeError:
                print("      JSON inválido")
                return None

        if r.status_code in (401, 403):
            sys.exit("cookies expirados (401/403) – atualize cookies.json")
        if r.status_code == 429:
            sys.exit("rate‑limit forte (429) – tente depois")

        if 500 <= r.status_code < 600:
            back = BACKOFF_FACTOR * (2 ** (attempt - 1))
            print(f"      {r.status_code} servidor – esperando {back:.1f}s")
            time.sleep(back)
            continue

        print(f"      status {r.status_code} não tratável")
        return None

    print("      excedeu tentativas")
    return None


def main(gc_id: int):
    # 1) descobrir quais IDs faltam
    wanted: set[int] = set()
    for hist in history_files(gc_id):
        wanted.update(match_ids(hist))

    stats_path = Path(STATS_DIR) / str(gc_id)
    stats_path.mkdir(parents=True, exist_ok=True)
    existing = {int(p.stem) for p in stats_path.glob("*.json")}
    missing_ids = sorted(wanted - existing)

    print(f"Total de partidas nos históricos : {len(wanted)}")
    print(f"Já baixadas localmente           : {len(existing)}")
    print(f"Faltando baixar                  : {len(missing_ids)}")

    if not missing_ids:
        print("✅ Nada a fazer.")
        return

    scraper = make_scraper(load_cookies(COOKIES_FILE))
    total_new = 0

    for idx, mid in enumerate(missing_ids, 1):
        print(f"  {mid} …", end="", flush=True)
        data = fetch_stats(scraper, mid)
        if not data:
            print("✗")
            continue

        with open(stats_path / f"{mid}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        total_new += 1
        print("✓")

        # pausa gentil
        if idx % 20 == 0:
            time.sleep(random.uniform(4, 6))
        else:
            time.sleep(random.uniform(1, 1.8))

    print(f"\n🏁 concluído – novos arquivos: {total_new}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        sys.exit("uso: python fetch_rpro_stats.py <gc_id>")
    from pathlib import Path
    main(int(sys.argv[1]))
