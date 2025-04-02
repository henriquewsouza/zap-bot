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
            print("Loaded match history:", match_history)
        except Exception as e:
            print("Error parsing match history JSON:", e)
            return

    for match in match_history:
        match_id = match.get("match_id")
        if not match_id:
            print("No match_id found for:", match)
            continue
        print(f"Processing match {match_id}...")
        # Call the get_single_match_stats.py script via subprocess
        result = subprocess.run(
            [sys.executable, "get_single_match_stats.py", str(match_id)],
            capture_output=True,
            text=True
        )
        print(f"Subprocess output for match {match_id}:")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    print("Finished processing all matches.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python load_match_stats.py <history_file>")
        sys.exit(1)
    history_file = sys.argv[1]
    load_match_stats(history_file)
