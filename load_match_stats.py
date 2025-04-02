import json
import subprocess
import boto3
import sys

BUCKET_NAME = "bucket-6sk08y"
ENDPOINT_URL = "https://s3.us-east-1.amazonaws.com"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)

def load_match_stats(history_s3_key):
    response = s3.get_object(Bucket=BUCKET_NAME, Key=history_s3_key)
    contents = response["Body"].read().decode("utf-8")
    try:
        match_history = json.loads(contents)
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
        # Capture output from the subprocess call to see any errors.
        result = subprocess.run(
            [sys.executable, "get_single_match_stats.py", str(match_id)],
            capture_output=True,
            text=True
        )
        print(f"Subprocess output for match {match_id}:")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    print("Finished processing all matches.")

