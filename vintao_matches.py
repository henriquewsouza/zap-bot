#!/usr/bin/env python3
# ───────────────────────────
#  fetch_rpro_stats.py
# ───────────────────────────
import os
import sys
import json
import time
import random
from typing import Optional, List, Dict

import requests
import cloudscraper

# ── CONFIGURÁVEIS ─────────────────────────────────────────────────────────
COOKIES_FILE = "cookies.json"          # cookies exportados do navegador
HISTORY_DIR  = "ranked_pro_matches"    # onde estão os históricos mensais
STATS_DIR    = "match_stats"           # para onde salvar os stats

TIMEOUT        = 20
MAX_RETRIES    = 3
BACKOFF_FACTOR = 1.5

BASE_HEADERS: Dict[str, str] = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "x-requested-with": "XMLHttpRequest",
}
# ──────────────────────────────────────────────────────────────────────────


def load_cookies(path: str) -> Dict[str, str]:
    """Lê cookies exportados do navegador e devolve dict nome→valor."""
    if not os.path.exists(path):
        sys.exit(f"[erro] {path} não encontrado – exporte os cookies primeiro.")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {c["name"]: c["value"] for c in raw}


def list_history_files(gc_id: int) -> List[str]:
    """Lista arquivos de histórico (JSON) para o jogador."""
    user_dir = os.path.join(HISTORY_DIR, str(gc_id))
    if not os.path.isdir(user_dir):
        sys.exit(f"[erro] Pasta {user_dir} não existe – rode o script de históricos antes.")
    return sorted(
        os.path.join(user_dir, f)
        for f in os.listdir(user_dir)
        if f.endswith(".json")
    )


def iter_match_ids(history_path: str) -> List[int]:
    """Extrai todos os IDs de partida de um arquivo de histórico."""
    with open(history_path, encoding="utf-8") as f:
        data = json.load(f)
    return [m["id"] for m in data if "id" in m]


def make_scraper(cookies: Dict[str, str]) -> cloudscraper.CloudScraper:
    """Cria CloudScraper com headers e cookies já aplicados."""
    scraper = cloudscraper.create_scraper()
    scraper.headers.update(BASE_HEADERS)
    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    scraper.headers["Cookie"] = cookie_header
    return scraper


def fetch_stats(scraper: cloudscraper.CloudScraper, match_id: int) -> Optional[dict]:
    """Baixa o JSON de stats da partida; respeita retries/back‑off."""
    url = f"https://gamersclub.com.br/lobby/match/{match_id}/1"
    headers = {"referer": f"https://gamersclub.com.br/lobby/match/{match_id}"}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = scraper.get(url, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            print(f"      erro de rede ({e})")
        else:
            code = resp.status_code
            if code == 200:
                try:
                    return resp.json()
                except json.JSONDecodeError:
                    print("      JSON inválido")
                    return None

            if code in (401, 403):
                sys.exit("      401/403 – cookies expirados, atualize o cookies.json.")
            if code == 429:
                sys.exit("      429 – rate‑limit forte, pare e tente depois.")
            if 500 <= code < 600:
                back = BACKOFF_FACTOR * (2 ** (attempt - 1))
                print(f"      {code} erro servidor → esperando {back:.1f}s")
                time.sleep(back)
                continue

            print(f"      status {code} não tratável")
            return None

    print("      excedeu tentativas")
    return None


def main(gc_id: int) -> None:
    cookies = load_cookies(COOKIES_FILE)
    scraper = make_scraper(cookies)
    os.makedirs(os.path.join(STATS_DIR, str(gc_id)), exist_ok=True)

    history_files = list_history_files(gc_id)
    total_new = 0

    for hist in history_files:
        print(f"\n📂 {os.path.basename(hist)}")
        for match_id in iter_match_ids(hist):
            out_file = os.path.join(STATS_DIR, str(gc_id), f"{match_id}.json")
            if os.path.exists(out_file):
                print(f"  {match_id} ✔︎ já existe")
                continue

            print(f"  {match_id} …", end="", flush=True)
            stats = fetch_stats(scraper, match_id)
            if stats is None:
                print("  ✗")
                continue

            with open(out_file, "w", encoding="utf-8") as f_out:
                json.dump(stats, f_out, indent=4, ensure_ascii=False)
            total_new += 1
            print("  ✓ salvo")

            time.sleep(random.uniform(1.0, 2.0))  # gentileza com o servidor

    print(f"\n🏁 concluído! Novos arquivos salvos: {total_new}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].isdigit():
        sys.exit("uso: python fetch_rpro_stats.py <gc_id>")
    main(int(sys.argv[1]))
