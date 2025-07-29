#!/usr/bin/env python3
"""
fetch_ranked_pro_pages.py
Baixa **todas** as partidas Ranked Pro do LKS (GC 859273),
paginando em /historyMatchesPage, e salva um arquivo por mês.
"""

import os, json, time, random, requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

GC_ID        = 859273
START_MONTH  = "2021-01"
OUT_DIR      = "ranked_pro_matches"        # raiz
COOKIES_FILE = "cookies.json"
RANKED_TYPES = {"ranked pro", "ranked_pro"}

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "user-agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/138.0.0.0 Safari/537.36"),
    "referer": f"https://gamersclub.com.br/jogador/{GC_ID}",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "dnt": "1",
}

def month_iter(start):
    cur = datetime.strptime(start, "%Y-%m")
    end = datetime.today().replace(day=1)
    while cur <= end:
        yield cur.strftime("%Y-%m")
        cur += relativedelta(months=1)

def load_cookie_header() -> str:
    with open(COOKIES_FILE, encoding="utf-8") as f:
        return "; ".join(f"{c['name']}={c['value']}" for c in json.load(f))

def make_session(cookie_header: str):
    s = requests.Session()
    s.headers.update(HEADERS)
    s.headers["Cookie"] = cookie_header
    return s

def fetch_page(sess, gc_id: int, yyyymm: str, page: int):
    url = f"https://gamersclub.com.br/api/box/historyMatchesPage/{gc_id}/{yyyymm}/{page}"
    r = sess.get(url, timeout=30)
    if r.status_code in (401, 403):
        raise RuntimeError("cookies expirados (401/403)")
    if r.status_code == 429:
        raise RuntimeError("rate‑limit (429)")
    r.raise_for_status()
    return r.json()

def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def main():
    sess   = make_session(load_cookie_header())
    total  = 0

    for month in month_iter(START_MONTH):
        month_matches = []
        page = 0
        while True:
            try:
                data = fetch_page(sess, GC_ID, month, page)
            except Exception as e:
                print(f"[{month} p{page}] erro: {e}")
                break

            matches = data.get("monthMatches", [])
            if not matches:
                break

            month_matches.extend(matches)
            print(f"{month} página {page}: {len(matches)} matches")
            page += 1
            time.sleep(random.uniform(0.8, 1.5))

        # filtra ranked pro
        ranked = [m for m in month_matches
                  if str(m.get("type", "")).lower() in RANKED_TYPES]

        if ranked:
            out = os.path.join(
                OUT_DIR, str(GC_ID), f"{GC_ID}-{month}-ranked_pro.json"
            )
            save_json(out, ranked)
            total += len(ranked)
            print(f"-- {month}: {len(ranked)} ranked pro salvas → {out}")
        else:
            print(f"-- {month}: 0 ranked pro")

    print(f"\n✅ Total geral Ranked Pro salvas: {total}")

if __name__ == "__main__":
    main()
