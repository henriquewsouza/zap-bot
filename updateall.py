import os
import json
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from match_history import get_match_history
from load_match_stats import load_match_stats
from aggregate_player_stats import aggregate_stats

MAX_WORKERS = 4

def process_member(gc_id, month_year):
    print(f"[{gc_id}] fetching history…")
    history_file = get_match_history(gc_id, month_year)
    print(f"[{gc_id}] loading match stats…")
    load_match_stats(history_file)
    print(f"[{gc_id}] aggregating stats…")
    aggregate_stats(gc_id, month_year)
    print(f"[{gc_id}] done.")

def git_commit_and_push(message="new stats"):
    """Stage all changes, commit with `message` and push to origin."""
    cmds = [
        ["git", "add", "."],
        ["git", "commit", "-m", message],
        ["git", "push"]
    ]
    for cmd in cmds:
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️ Command failed: {' '.join(cmd)}")
            print("STDOUT:", result.stdout.strip())
            print("STDERR:", result.stderr.strip())
            # decide whether to abort or continue; here we abort on failure:
            return False
    return True

def main():
    members_file = "members.json"
    if not os.path.exists(members_file):
        print("members.json not found in the root folder.")
        return

    with open(members_file, encoding="utf-8") as f:
        members_data = json.load(f)

    month_year = datetime.now().strftime("%Y-%m")

    # 1) Parallel processing of members
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_member, info["gc"], month_year): discord_id
            for discord_id, info in members_data.items()
            if info.get("gc")
        }
        for fut in as_completed(futures):
            dc_id = futures[fut]
            try:
                fut.result()
            except Exception as e:
                print(f"⚠️ Error for Discord ID {dc_id}: {e}")

    print("✅ Update complete for all members.")

    # 2) Git add/commit/push
    if git_commit_and_push("new stats"):
        print("✅ Changes committed and pushed.")
    else:
        print("❌ Git push failed; please check errors above.")

if __name__ == "__main__":
    main()
