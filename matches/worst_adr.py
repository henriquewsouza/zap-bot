#!/usr/bin/env python3
import os
import json
import argparse
import subprocess
from typing import List, Tuple, Optional, Dict, Any

# =====================================================================
# >>> HARD-CODED PLAYER ID AQUI <<<
# LKS!  (mude para o ID que quiser como padrão)
PLAYER_ID_CONST = "1315017"
# =====================================================================

URL_TEMPLATE_DEFAULT = "https://gamersclub.com.br/lobby/match/{id}"

# ---------- utils ----------
def _safe_float(x) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def _safe_int(x) -> Optional[int]:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None

def _player_matches(p: Dict[str, Any], target_id: str) -> bool:
    tid = str(target_id)
    if str(p.get("idplayer")) == tid:
        return True
    pl = p.get("player") or {}
    if str(pl.get("id")) == tid:
        return True
    if str(p.get("complete_for")) == tid:
        return True
    return False

def _calc_adr(p: Dict[str, Any]) -> Optional[float]:
    adr = _safe_float(p.get("adr"))
    if adr is not None:
        return adr
    dmg = _safe_float(p.get("damage"))
    rnds = _safe_int(p.get("rounds_played"))
    if dmg is not None and rnds and rnds > 0:
        return dmg / rnds
    return None

def _open_chrome(url: str) -> None:
    # macOS: abre no Google Chrome (ignora erros)
    subprocess.run(["open", "-a", "Google Chrome", url], check=False)

# ---------- core ----------
def find_worst_matches(
    player_id: str,
    matches_dir: str,
    top_n: int = 10,
    min_rounds: int = 0,
) -> List[Tuple[float, str, str, str, int, int, int, int]]:
    """
    Retorna até top_n partidas ordenadas por ADR crescente (piores primeiro).
    Item: (adr, match_id, data_str, map_name, kills, deaths, damage, rounds)
    """
    recs: List[Tuple[float, str, str, str, int, int, int, int]] = []
    for root, _, files in os.walk(matches_dir):
        for fname in files:
            if not fname.lower().endswith(".json"):
                continue
            path = os.path.join(root, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            match_id = data.get("id") or os.path.splitext(fname)[0]
            match_date = data.get("data")

            jogos = data.get("jogos", {})
            map_name = jogos.get("map_name", "unknown")
            players = jogos.get("players", {})
            all_p = players.get("team_a", []) + players.get("team_b", [])
            if not all_p:
                continue

            p = next((p for p in all_p if _player_matches(p, player_id)), None)
            if not p:
                continue

            adr = _calc_adr(p)
            if adr is None:
                continue

            rounds = _safe_int(p.get("rounds_played")) or 0

            kills = _safe_int(p.get("nb_kill")) or 0
            deaths = _safe_int(p.get("death")) or 0
            damage = _safe_int(p.get("damage")) or 0

            recs.append((adr, match_id, match_date, map_name, kills, deaths, damage, rounds))

    recs.sort(key=lambda r: r[0])  # menor ADR primeiro
    return recs[:top_n]

# ---------- cli ----------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Piores partidas (menor ADR) de um jogador da GamersClub (usa PLAYER_ID_CONST se nenhum ID for passado)."
    )
    p.add_argument("player", nargs="?", help="GC ID do jogador (se omitido, usa PLAYER_ID_CONST).")
    p.add_argument(
        "-d", "--dir", default=".",
        help="Diretório com arquivos de partidas (.json). Default: diretório atual."
    )
    p.add_argument("-n", "--top", type=int, default=10, help="Quantas piores partidas retornar. Default: 10.")
    p.add_argument("--min-rounds", type=int, default=0, help="Mínimo de rounds jogados para considerar a partida.")
    p.add_argument("--ids-only", action="store_true", help="Imprime apenas os match IDs (um por linha).")
    p.add_argument("--open-chrome", action="store_true", help="Abre as partidas no Google Chrome.")
    p.add_argument("--url-template", default=URL_TEMPLATE_DEFAULT,
                   help="Template da URL. Use {id}. Default: %(default)s")
    return p.parse_args()

def main():
    args = parse_args()
    # Usa arg se passado; senão constante
    player_id = args.player.strip() if args.player else PLAYER_ID_CONST
    matches_dir = args.dir

    recs = find_worst_matches(
        player_id=player_id,
        matches_dir=matches_dir,
        top_n=args.top,
        min_rounds=args.min_rounds,
    )

    if not recs:
        print(f"Nenhuma partida válida encontrada para player {player_id} em '{matches_dir}'.")
        return

    if args.ids_only and not args.open_chrome:
        for _, match_id, *_ in recs:
            print(match_id)
        return

    print(f"Piores {len(recs)} partidas de {player_id} (menor ADR) em '{matches_dir}':")
    worst = recs[0]
    print(
        f"\nPior ADR: Match {worst[1]} | ADR={worst[0]:.2f} | Data={worst[2]} | Mapa={worst[3]} | "
        f"K/D={worst[4]}/{worst[5]} | Damage={worst[6]} | Rounds={worst[7]}\n"
    )

    print("Lista completa:")
    for adr, mid, dt, mp, k, d, dmg, rnds in recs:
        print(f"  • {mid}: ADR={adr:.2f} | {dt} | {mp} | {k}/{d} K/D | dmg={dmg} | rnds={rnds}")

    if args.open_chrome:
        print("\nAbrindo no Chrome...")
        for _, mid, *_ in recs:
            url = args.url_template.format(id=mid)
            _open_chrome(url)

if __name__ == "__main__":
    main()
