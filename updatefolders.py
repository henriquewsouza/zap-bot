import os
import boto3

# S3 Configuration
BUCKET_NAME = "bucket-6sk08y"
ENDPOINT_URL = "https://s3.us-east-1.amazonaws.com"
s3 = boto3.client("s3", endpoint_url=ENDPOINT_URL)

def delete_folder(prefix):
    """Delete all objects in S3 bucket with the given prefix."""
    print(f"Deleting objects under prefix '{prefix}' from bucket '{BUCKET_NAME}'...")
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix)
    
    keys_to_delete = []
    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                keys_to_delete.append({'Key': obj['Key']})
    
    if keys_to_delete:
        response = s3.delete_objects(
            Bucket=BUCKET_NAME,
            Delete={'Objects': keys_to_delete}
        )
        print(f"Deleted {len(keys_to_delete)} objects under '{prefix}'.")
    else:
        print(f"No objects found under prefix '{prefix}'.")

def upload_folder(local_folder, s3_prefix):
    """
    Uploads all files in the local folder (and subfolders) to S3,
    using the specified s3_prefix as the root key.
    """
    print(f"Uploading local folder '{local_folder}' to S3 prefix '{s3_prefix}'...")
    for root, _, files in os.walk(local_folder):
        for file in files:
            local_path = os.path.join(root, file)
            # Compute the S3 key by removing the local folder part and adding s3_prefix.
            relative_path = os.path.relpath(local_path, local_folder)
            s3_key = os.path.join(s3_prefix, relative_path).replace("\\", "/")
            print(f"Uploading {local_path} as {s3_key}...")
            s3.upload_file(local_path, BUCKET_NAME, s3_key)
    print(f"Upload of '{local_folder}' complete.")

def main():
    # Delete existing "folders" on S3
    delete_folder("matches/")
    delete_folder("players/")
    
    # Upload local folders to S3
    if os.path.isdir("matches"):
        upload_folder("matches", "matches/")
    else:
        print("Local folder 'matches' not found.")
    
    if os.path.isdir("players"):
        upload_folder("players", "players/")
    else:
        print("Local folder 'players' not found.")

if __name__ == "__main__":
    main()
