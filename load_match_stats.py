import json
import subprocess
import boto3
import sys

BUCKET_NAME = "bucket-6sk08y"
ENDPOINT_URL = "https://s3.us-east-1.amazonaws.com"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)

def load_match_stats(history_s3_key):
    """
    Downloads the match history file from S3 (given its key) and for each match,
    calls fetch_match_stats (via subprocess) to ensure full stats are stored on S3.
    """
    response = s3.get_object(Bucket=BUCKET_NAME, Key=history_s3_key)
    contents = response["Body"].read().decode("utf-8")
    match_history = json.loads(contents)
    for match in match_history:
        match_id = match.get("match_id")
        if not match_id:
            continue
        print(f"Processing match {match_id}...")
        subprocess.run([sys.executable, "get_single_match_stats.py", str(match_id)])
    print("Finished processing all matches.")
