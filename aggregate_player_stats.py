# aggregate_player_stats.py
import os
import json
import glob
from datetime import datetime

def aggregate_stats(gc_id, month_year):
    """
    Aggregates match stats for the given GC id (player) for the specified month.
    Reads match files from the 'matches' folder, filters by month, and
    sums overall and per-map stats (kills, deaths, damage, rounds, etc.).
    Saves aggregated stats to /players/{gc_id}/stats-{month_year}.json.
    """
    match_files = glob.glob(os.path.join("matches", "*.json"))

    # Initialize overall aggregates
    total_matches = 0
    total_wins = 0
    total_kills = 0
    total_deaths = 0
    total_damage = 0
    total_rounds = 0
    total_first_kills = 0
    total_headshots = 0

    # Per-map aggregates (including deaths, damage, rounds)
    per_map = {}

    for file_path in match_files:
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

        match_date_str = data.get("data")
        if not match_date_str:
            continue

        try:
            match_date = datetime.strptime(match_date_str, "%d/%m/%Y %H:%M")
        except Exception as e:
            print(f"Error parsing date in {file_path}: {e}")
            continue

        if match_date.strftime("%Y-%m") != month_year:
            continue

        # Find the player's stats in jogos -> players (GC id is used)
        jogos = data.get("jogos", {})
        players_data = jogos.get("players", {})
        player_found = None
        player_team = None
        for team in ["team_a", "team_b"]:
            for p in players_data.get(team, []):
                if str(p.get("idplayer")) == str(gc_id):
                    player_found = p
                    player_team = team
                    break
            if player_found:
                break
        if not player_found:
            continue

        total_matches += 1
        try:
            kills = int(player_found.get("nb_kill", 0))
            deaths = int(player_found.get("death", 0))
            damage = int(player_found.get("damage", 0))
            rounds_played = int(player_found.get("rounds_played", 0))
            first_kill = int(player_found.get("firstkill", 0))
            headshots = int(player_found.get("hs", 0))
        except Exception as e:
            print(f"Error converting stats in {file_path}: {e}")
            continue

        total_kills += kills
        total_deaths += deaths
        total_damage += damage
        total_rounds += rounds_played
        total_first_kills += first_kill
        total_headshots += headshots

        try:
            score_a = int(jogos.get("score_a", "0"))
            score_b = int(jogos.get("score_b", "0"))
        except Exception:
            score_a, score_b = 0, 0

        winning_team = None
        if score_a > score_b:
            winning_team = "team_a"
        elif score_b > score_a:
            winning_team = "team_b"
        win = (player_team == winning_team) if winning_team is not None else False
        if win:
            total_wins += 1

        map_name = jogos.get("map_name", "unknown")
        if map_name not in per_map:
            per_map[map_name] = {
                "matches": 0,
                "wins": 0,
                "kills": 0,
                "deaths": 0,
                "damage": 0,
                "rounds": 0
            }
        per_map[map_name]["matches"] += 1
        per_map[map_name]["kills"] += kills
        per_map[map_name]["deaths"] += deaths
        per_map[map_name]["damage"] += damage
        per_map[map_name]["rounds"] += rounds_played
        if win:
            per_map[map_name]["wins"] += 1

    overall_losses = total_matches - total_wins
    overall_KDR = total_kills / total_deaths if total_deaths > 0 else float(total_kills)
    overall_ADR = total_damage / total_rounds if total_rounds > 0 else 0
    overall_win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0
    overall_HS_percent = (total_headshots / total_kills * 100) if total_kills > 0 else 0
    average_first_kills_per_match = total_first_kills / total_matches if total_matches > 0 else 0

    per_map_stats = {}
    for m, stats in per_map.items():
        matches_map = stats["matches"]
        wins_map = stats["wins"]
        win_rate_map = (wins_map / matches_map * 100) if matches_map > 0 else 0
        kills_map = stats["kills"]
        deaths_map = stats["deaths"]
        damage_map = stats["damage"]
        rounds_map = stats["rounds"]
        kdr_map = kills_map / deaths_map if deaths_map > 0 else kills_map
        adr_map = damage_map / rounds_map if rounds_map > 0 else 0
        per_map_stats[m] = {
            "matches": matches_map,
            "wins": wins_map,
            "win_rate": win_rate_map,
            "kills": kills_map,
            "deaths": deaths_map,
            "damage": damage_map,
            "rounds": rounds_map,
            "kdr": kdr_map,
            "adr": adr_map
        }

    aggregated_stats = {
        "player_id": gc_id,
        "month_year": month_year,
        "total_matches": total_matches,
        "total_wins": total_wins,
        "total_losses": overall_losses,
        "overall_win_rate": overall_win_rate,
        "total_kills": total_kills,
        "total_deaths": total_deaths,
        "KDR": overall_KDR,
        "total_damage": total_damage,
        "total_rounds": total_rounds,
        "ADR": overall_ADR,
        "total_first_kills": total_first_kills,
        "average_first_kills_per_match": average_first_kills_per_match,
        "total_headshots": total_headshots,
        "HS_percent": overall_HS_percent,
        "per_map": per_map_stats
    }

    players_folder = os.path.join("players", str(gc_id))
    os.makedirs(players_folder, exist_ok=True)
    stats_file = os.path.join(players_folder, f"stats-{month_year}.json")
    with open(stats_file, "w") as f:
        json.dump(aggregated_stats, f, indent=4)
    print(f"Aggregated stats for {gc_id} saved to {stats_file}")

if __name__ == "__main__":
    player_id = input("Enter the GC player id: ").strip()
    month_year = datetime.now().strftime("%Y-%m")
    aggregate_stats(player_id, month_year)
