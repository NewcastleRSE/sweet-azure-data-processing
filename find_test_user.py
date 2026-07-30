import os
import json
from collections import defaultdict
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "users")


def count_json_elements_and_keys(data):
    """Calculates record count and total key count for any JSON structure."""
    record_count = 0
    key_count = 0

    if isinstance(data, list):
        record_count += len(data)
        for item in data:
            if isinstance(item, dict):
                key_count += len(item.keys())
                # Recurse one level deep if items have nested dicts
                for v in item.values():
                    if isinstance(v, dict):
                        key_count += len(v.keys())
            else:
                key_count += 1

    elif isinstance(data, dict):
        record_count += len(data.keys())
        key_count += len(data.keys())
        for v in data.values():
            if isinstance(v, dict):
                key_count += len(v.keys())
            elif isinstance(v, list):
                record_count += len(v)

    return record_count, key_count


def find_most_complete_user(connection_string: str, container_name: str):
    if not connection_string:
        raise ValueError("Missing AZURE_STORAGE_CONNECTION_STRING in environment or .env file.")

    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)

    # Structure: { user_id: { "blobs": set(), "records": int, "total_keys": int, "byte_size": int } }
    user_metrics = defaultdict(lambda: {
        "blobs": set(),
        "records": 0,
        "total_keys": 0,
        "byte_size": 0
    })

    print(f"Scanning container '{container_name}/userdata/' across ALL users...\n")

    blobs = container_client.list_blobs(name_starts_with="userdata/")

    for blob in blobs:
        # Skip placeholder files
        if blob.size == 0 or blob.name.lower().endswith("_init"):
            continue

        parts = blob.name.split("/")
        if len(parts) < 3:
            continue

        user_id = parts[1]
        blob_filename = "/".join(parts[2:])
        blob_type = blob_filename.replace(".json", "")

        user_metrics[user_id]["blobs"].add(blob_type)
        user_metrics[user_id]["byte_size"] += blob.size

        # Inspect blob content for record/key richness
        try:
            blob_client = container_client.get_blob_client(blob.name)
            download_stream = blob_client.download_blob()
            data = json.loads(download_stream.readall())

            records, keys = count_json_elements_and_keys(data)
            user_metrics[user_id]["records"] += records
            user_metrics[user_id]["total_keys"] += keys

        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"⚠️ Error parsing blob '{blob.name}': {e}")

    # Rank users by:
    # 1. Number of unique blob types (most diverse data)
    # 2. Total populated key count (most comprehensive fields)
    # 3. Total byte size
    sorted_users = sorted(
        user_metrics.items(),
        key=lambda x: (len(x[1]["blobs"]), x[1]["total_keys"], x[1]["byte_size"]),
        reverse=True
    )

    print_user_ranking_report(sorted_users)


def print_user_ranking_report(sorted_users, top_n=5):
    """Prints a clean summary of the top N users with the most complete data."""
    print("=" * 75)
    print(f"TOP {top_n} CANDIDATE USERS FOR RE-PLATFORMING TEST")
    print("=" * 75)

    if not sorted_users:
        print("No user data found in container.")
        return

    # Winner
    top_user_id, top_stats = sorted_users[0]
    print(f"\n🏆 RECOMMENDED TEST USER: [ {top_user_id} ]")
    print(f"   └── Blob Diversity : {len(top_stats['blobs'])} different blob types")
    print(f"   └── Total Records  : {top_stats['records']} entries/rows")
    print(f"   └── Key Richness   : {top_stats['total_keys']} populated JSON keys")
    print(f"   └── Total Size     : {top_stats['byte_size'] / 1024:.2f} KB")
    print(f"   └── Available Blobs: {', '.join(sorted(top_stats['blobs']))}")

    print("\n" + "-" * 75)
    print(f"RUNNER-UP USER CANDIDATES (TOP {top_n}):")
    print("-" * 75)

    for rank, (user_id, stats) in enumerate(sorted_users[1:top_n], start=2):
        print(f" #{rank} User ID: [ {user_id:<15} ] | Blobs: {len(stats['blobs']):<2} | Keys: {stats['total_keys']:<5} | Size: {stats['byte_size']/1024:.2f} KB")
        print(f"    └── Blobs present: {', '.join(sorted(stats['blobs']))}")


if __name__ == "__main__":
    find_most_complete_user(
        connection_string=CONNECTION_STRING,
        container_name=CONTAINER_NAME,
    )