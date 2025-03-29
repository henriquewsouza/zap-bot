# load_match_stats.py
import json
import subprocess
import os

def load_match_stats(history_file):
    """
    For each match in the given history file, ensures full match stats are downloaded
    by calling the fetch_match_stats function via a subprocess call.
    """
    with open(history_file, "r") as f:
        match_history = json.load(f)
    for match in match_history:
        match_id = match.get("match_id")
        if not match_id:
            continue
        print(f"Processing match {match_id}...")
        subprocess.run(["python", "get_single_match_stats.py", str(match_id)])
    print("Finished processing all matches.")
