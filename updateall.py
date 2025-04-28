#!/usr/bin/env python3
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
    hist = get_match_history(gc_id, month_year)
    print(f"[{gc_id}] loading match stats…")
    load_match_stats(hist)
    print(f"[{gc_id}] aggregating stats…")
    aggregate_stats(gc_id, month_year)
    print(f"[{gc_id}] done.")

def git_commit_and_push(msg="new stats"):
    for cmd in (["git","add","."], ["git","commit","-m",msg], ["git","push"]):
        print("→", " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print("✖", r.stderr.strip())
            return False
    return True

def main():
    if not os.path.exists("members.json"):
        return print("members.json missing")

    data = json.load(open("members.json", encoding="utf-8"))
    mon  = datetime.now().strftime("%Y-%m")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {
            ex.submit(process_member, info["gc"], mon): dc
            for dc, info in data.items() if info.get("gc")
        }
        for fut in as_completed(futures):
            dc = futures[fut]
            try: fut.result()
            except Exception as e:
                print(f"⚠️ {dc} failed:", e)

    print("✅ All members done.")

    if git_commit_and_push():
        print("✅ Pushed to repo")
    else:
        print("❌ Git steps failed, please check above")

if __name__ == "__main__":
    main()
