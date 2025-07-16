#!/usr/bin/env python3
import os
import json
import argparse
from typing import List, Tuple, Optional

def _player_matches_id(p: dict, target_id: str, consider_complete_for: bool = True) -> bool:
    """
    Retorna True se o jogador p corresponde ao target_id em qualquer um dos campos esperados.
    """
    tid = str(target_id)
    if str(p.get("idplayer")) == tid:
        return True
    # campo aninhado
    player_obj = p.get("player") or {}
    if str(player_obj.get("id")) == tid:
        return True
    if consider_complete_for and str(p.get("complete_for")) == tid:
        # caso o jogador tenha sido substituído e o registro esteja em 'complete_for'
        return True
    return False

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

def get_top_matches(
    player1_id: str,
    player2_id: str,
    matches_dir: str,
    top_n: int = 10,
    min_rounds: int = 0,
    consider_complete_for: bool = True,
    only_positive_diff: bool = True,
) -> List[Tuple[str, float]]:
    """
    Percorre todos os arquivos JSON em matches_dir (recursivo), busca os dois jogadores e calcula
    diff de ADR (p1 - p2). Retorna top_n partidas ordenadas por diff decrescente.
    """
    diffs = []
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

            players_by_team = data.get("jogos", {}).get("players", {})
            all_players = players_by_team.get("team_a", []) + players_by_team.get("team_b", [])
            if not all_players:
                continue

            p1 = next((p for p in all_players if _player_matches_id(p, player1_id, consider_complete_for)), None)
            p2 = next((p for p in all_players if _player_matches_id(p, player2_id, consider_complete_for)), None)
            if not p1 or not p2:
                continue

            adr1 = _safe_float(p1.get("adr"))
            adr2 = _safe_float(p2.get("adr"))
            if adr1 is None or adr2 is None:
                # Se ADR não veio calculado no JSON, tentar derivar: damage/rounds
                dmg1 = _safe_float(p1.get("damage"))
                rnd1 = _safe_int(p1.get("rounds_played"))
                dmg2 = _safe_float(p2.get("damage"))
                rnd2 = _safe_int(p2.get("rounds_played"))
                if adr1 is None and dmg1 is not None and rnd1 and rnd1 > 0:
                    adr1 = dmg1 / rnd1
                if adr2 is None and dmg2 is not None and rnd2 and rnd2 > 0:
                    adr2 = dmg2 / rnd2
            # Se ainda não temos ambos, pula
            if adr1 is None or adr2 is None:
                continue

            # filtro de mínimo de rounds
            if min_rounds > 0:
                r1 = _safe_int(p1.get("rounds_played")) or 0
                r2 = _safe_int(p2.get("rounds_played")) or 0
                if r1 < min_rounds or r2 < min_rounds:
                    continue

            diff = adr1 - adr2
            if only_positive_diff and diff <= 0:
                continue

            diffs.append((match_id, diff))

    diffs.sort(key=lambda x: x[1], reverse=True)
    return diffs[:top_n]

def resolve_default_dir(user_dir_arg: Optional[str]) -> str:
    """
    Resolve qual diretório usar:
    1. Se usuário passou explicitamente, usa.
    2. Se não passou e existe ./matches no CWD, usa.
    3. Se não existe, usa o diretório do script.
    4. Se tudo falhar, usa CWD.
    """
    if user_dir_arg:
        return user_dir_arg
    cwd_matches = os.path.join(os.getcwd(), "matches")
    if os.path.isdir(cwd_matches):
        return cwd_matches
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_matches = os.path.join(script_dir, "matches")
    if os.path.isdir(script_matches):
        return script_matches
    return os.getcwd()

def main():
    parser = argparse.ArgumentParser(
        description="Top N partidas onde o player1 teve maior ADR que o player2."
    )
    parser.add_argument("player1", help="GC ID do primeiro jogador (ex: 829311)")
    parser.add_argument("player2", help="GC ID do segundo jogador (ex: 1315017)")
    parser.add_argument("-d", "--dir", help="Diretório com os JSONs de partidas. Se omitido, tento descobrir.")
    parser.add_argument("-n", "--topn", type=int, default=10, help="Quantidade de partidas a retornar (padrão: 10).")
    parser.add_argument("--min-rounds", type=int, default=0, help="Mínimo de rounds jogados por cada jogador.")
    parser.add_argument("--allow-negative", action="store_true", help="Inclui diffs negativos (p1 foi pior).")

    parser.add_argument("--no-complete-for", action="store_true",
                        help="Não considerar o campo 'complete_for' para identificar o jogador.")

    args = parser.parse_args()
    matches_dir = resolve_default_dir(args.dir)

    results = get_top_matches(
        player1_id=str(args.player1),
        player2_id=str(args.player2),
        matches_dir=matches_dir,
        top_n=args.topn,
        min_rounds=args.min_rounds,
        consider_complete_for=not args.no_complete_for,
        only_positive_diff=not args.allow_negative,
    )

    if not results:
        print(f"Nenhuma partida encontrada entre {args.player1} e {args.player2} em '{matches_dir}'.")
        return

    print(f"Top {len(results)} partidas com maior diferença de ADR ({args.player1} - {args.player2}) em '{matches_dir}':")
    for mid, diff in results:
        print(f"  • {mid}: diff ADR = {diff:.2f}")

if __name__ == "__main__":
    main()
