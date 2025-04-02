import os
import json
from datetime import datetime
from match_history import get_match_history
from load_match_stats import load_match_stats
from aggregate_player_stats import aggregate_stats

def process_member(gc_id, month_year):
    print(f"Processing member with GC id: {gc_id}")
    # Get the match history for this GC id and month.
    history_file = get_match_history(gc_id, month_year)
    
    # Load (and fetch) match stats for every match in the history.
    load_match_stats(history_file)
    
    # Aggregate the player's stats and save locally.
    aggregate_stats(gc_id, month_year)

def main():
    members_file = "members.json"  # Local members file
    if not os.path.exists(members_file):
        print("members.json not found in the root folder.")
        return

    with open(members_file, "r", encoding="utf-8") as f:
        members_data = json.load(f)
    
    month_year = datetime.now().strftime("%Y-%m")
    for discord_id, info in members_data.items():
        gc_id = info.get("gc")
        if not gc_id:
            print(f"Skipping Discord ID {discord_id}: no GC id set.")
            continue
        print(f"Updating stats for GC id: {gc_id} for {month_year}...")
        process_member(gc_id, month_year)
    
    print("Update complete for all members.")

if __name__ == "__main__":
    main()
