import os
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed

BUCKET_NAME  = "bucket-6sk08y"
ENDPOINT_URL = "https://s3.us-east-1.amazonaws.com"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)

MAX_WORKERS = 10


def delete_folder(prefix):
    """Delete all objects in S3 bucket with the given prefix."""
    paginator = s3.get_paginator('list_objects_v2')
    to_delete = []
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get('Contents', []):
            to_delete.append({'Key': obj['Key']})
    if to_delete:
        s3.delete_objects(Bucket=BUCKET_NAME, Delete={'Objects': to_delete})
        print(f"➖ Deleted {len(to_delete)} objects under '{prefix}'")
    else:
        print(f"⚪ No objects to delete under '{prefix}'")


def list_existing_keys(prefix):
    """Return a set of all object keys under the given prefix."""
    paginator = s3.get_paginator("list_objects_v2")
    existing = set()
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            existing.add(obj["Key"])
    return existing


def _upload_file(local_path, s3_key):
    """Helper to upload one file."""
    try:
        s3.upload_file(local_path, BUCKET_NAME, s3_key)
        return f"✅ Uploaded: {s3_key}"
    except Exception as e:
        return f"❗ Error uploading {s3_key}: {e}"


def upload_folder(local_folder, s3_prefix):
    """Upload every file under local_folder to s3_prefix, in parallel."""
    tasks = []
    for root, _, files in os.walk(local_folder):
        for fn in files:
            local_path = os.path.join(root, fn)
            rel_path   = os.path.relpath(local_path, local_folder).replace("\\","/")
            s3_key     = f"{s3_prefix.rstrip('/')}/{rel_path}"
            tasks.append((local_path, s3_key))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_upload_file, lp, key): key for lp, key in tasks}
        for fut in as_completed(futures):
            print(fut.result())


def upload_new_only(local_folder, s3_prefix):
    """Upload only files not already present under s3_prefix, in parallel."""
    existing = list_existing_keys(s3_prefix)
    tasks = []
    for root, _, files in os.walk(local_folder):
        for fn in files:
            local_path = os.path.join(root, fn)
            rel_path   = os.path.relpath(local_path, local_folder).replace("\\","/")
            s3_key     = f"{s3_prefix.rstrip('/')}/{rel_path}"
            if s3_key not in existing:
                tasks.append((local_path, s3_key))

    if not tasks:
        print("⚪ No new match files to upload.")
        return

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_upload_file, lp, key): key for lp, key in tasks}
        for fut in as_completed(futures):
            print(fut.result())


def main():
    # 1) Full replace players/
    delete_folder("players/")
    if os.path.isdir("players"):
        print("📂 Syncing players/ (full refresh)…")
        upload_folder("players", "players/")
    else:
        print("⚠️ Local 'players/' folder not found.")

    # 2) Append-only matches/
    if os.path.isdir("matches"):
        print("📂 Syncing matches/ (incremental)…")
        upload_new_only("matches", "matches/")
    else:
        print("⚠️ Local 'matches/' folder not found.")


if __name__ == "__main__":
    main()
