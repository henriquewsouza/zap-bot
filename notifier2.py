# next_game_tester.py
"""
Simples GET em TheSportsDB para pegar o próximo jogo do Bahia
(usando o endpoint eventsnext.php).
"""

import requests
import sys

# ─── CONFIGURAÇÃO ────────────────────────────────────────────────
API_KEY = "123"            # substitua se precisar usar outra key
TEAM_ID = "134293"         # ID do Bahia no TheSportsDB
URL     = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}/eventsnext.php?id={TEAM_ID}"

def main():
    try:
        print(f"▶️  GET {URL}")
        resp = requests.get(URL, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("❌ Erro na requisição:", e)
        sys.exit(1)

    try:
        data = resp.json()
    except ValueError as e:
        print("❌ Não foi possível decodificar JSON:", e)
        print("Resposta bruta:", resp.text[:500])
        sys.exit(1)

    events = data.get("events") or []
    if not events:
        print("🚫 Nenhum próximo jogo encontrado.")
        return

    # normalmente retorna uma lista, mas pegamos apenas o primeiro
    ev = events[0]
    print("✅ Próximo jogo encontrado:")
    print(f"  • Evento:      {ev.get('strEvent')}")
    print(f"  • Data:        {ev.get('dateEvent')}")
    print(f"  • Horário:     {ev.get('strTimeLocal')}")
    print(f"  • Competição:  {ev.get('strLeague')}")
    print(f"  • Descrição:   {ev.get('strDescriptionEN') or '–'}")

if __name__ == "__main__":
    main()
