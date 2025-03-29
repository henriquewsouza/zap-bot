# aggregate_all_members.py
import os
import json
from datetime import datetime
from match_history import get_match_history
from load_match_stats import load_match_stats
from aggregate_player_stats import aggregate_stats

def process_member(gc_id, month_year):
    print(f"Processing member with GC id: {gc_id}")
    history_file = get_match_history(gc_id, month_year)
    load_match_stats(history_file)
    aggregate_stats(gc_id, month_year)

def main():
    members_file = "members.json"
    if not os.path.exists(members_file):
        print("members.json not found in root folder.")
        return
    with open(members_file, "r") as f:
        members_data = json.load(f)
    month_year = datetime.now().strftime("%Y-%m")
    for discord_id, info in members_data.items():
        gc_id = info.get("gc")
        if not gc_id:
            print(f"Skipping Discord ID {discord_id} as no GC id is set.")
            continue
        process_member(gc_id, month_year)

if __name__ == "__main__":
    main()
