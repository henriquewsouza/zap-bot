import json
import subprocess
import sys
import os

def load_match_stats(history_file):
    if not os.path.exists(history_file):
        print(f"History file {history_file} not found.")
        return

    with open(history_file, "r", encoding="utf-8") as f:
        try:
            match_history = json.load(f)
        except Exception as e:
            print("Error parsing match history JSON:", e)
            return
        
    stats_dir = os.path.join(os.getcwd(), "matches")

    if not os.path.isdir(stats_dir):
        print(f"Warning: stats_dir {stats_dir} doesn’t exist yet.")
        
    for match in match_history:
        match_id = match.get("match_id")
        if not match_id:
            print("No match_id found for:", match)
            continue

        # build the expected stats filename
        stats_file = os.path.join(stats_dir, f"{match_id}.json")
        if os.path.exists(stats_file):
            print(f"Stats for match {match_id} already exist ({stats_file}), skipping.")
            continue

        print(f"Processing match {match_id}…")
        result = subprocess.run(
            [sys.executable, "get_single_match_stats.py", str(match_id)],
            capture_output=True,
            text=True
        )
        print(f"Subprocess output for match {match_id}:")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)

    print("Finished processing all matches.")
