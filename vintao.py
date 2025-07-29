import os
import json
import time
import random
from datetime import datetime
from dateutil.relativedelta import relativedelta
import requests

GC_ID = 859273
START_MONTH = "2021-01"
BASE_DIR = "ranked_solo_matches"
COOKIES_FILE = "cookies.json"

# Headers mínimos; o cookie leva as credenciais.
BASE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "referer": f"https://gamersclub.com.br/jogador/{GC_ID}",
    "accept-language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "dnt": "1",
}

def month_iter(start_yyyymm: str):
    cur = datetime.strptime(start_yyyymm, "%Y-%m")
    end = datetime.today().replace(day=1)
    while cur <= end:
        yield cur.strftime("%Y-%m")
        cur += relativedelta(months=1)

def load_cookies_from_file(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def build_cookie_header(cookies: list[dict]) -> str:
    # Monta "name=value; name2=value2; ..."
    parts = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)

def make_session(cookies_json: list[dict]) -> requests.Session:
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    # Preferir header "Cookie" para garantir envio com o domínio correto.
    cookie_header = build_cookie_header(cookies_json)
    s.headers["Cookie"] = cookie_header
    return s

def fetch_month(session: requests.Session, gc_id: int, month_yyyymm: str) -> list[dict]:
    url = f"https://gamersclub.com.br/api/box/historyFilterDate/{gc_id}/{month_yyyymm}"
    resp = session.get(url, timeout=30)
    # Tratar rate limit / auth expirada de forma amigável
    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"Acesso negado ({resp.status_code}) em {month_yyyymm}. "
            f"Atualize os cookies em {COOKIES_FILE} e tente novamente."
        )
    if resp.status_code == 429:
        raise RuntimeError("Rate limited (429). Tente novamente mais tarde.")
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("monthMatches", []) or []

def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def main():
    cookies_json = load_cookies_from_file(COOKIES_FILE)
    session = make_session(cookies_json)

    total_saved = 0
    for month in month_iter(START_MONTH):
        try:
            print(f"⬇️  Buscando {month} ...", end=" ", flush=True)
            matches = fetch_month(session, GC_ID, month)
            ranked = [m for m in matches if m.get("type") == "ranked pro"]
            if ranked:
                out_path = os.path.join(
                    BASE_DIR, str(GC_ID), f"{GC_ID}-{month}-ranked pro.json"
                )
                save_json(out_path, ranked)
                total_saved += len(ranked)
                print(f"↳ {len(ranked)} partidas salvas → {out_path}")
            else:
                print("sem ranked pro")
        except Exception as e:
            print(f"\n⚠️  Falhou em {month}: {e}")
            # Em caso de erro de auth/rate-limit, parar pode ser melhor:
            if any(msg in str(e) for msg in ("Acesso negado", "Rate limited")):
                break
        # Pausa curta aleatória (boa prática para evitar bloqueios)
        time.sleep(random.uniform(1.0, 2.0))

    print(f"\n✅ Concluído. Total de partidas ranked_solo salvas: {total_saved}")

if __name__ == "__main__":
    main()
