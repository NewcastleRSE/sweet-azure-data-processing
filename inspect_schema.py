import json
import os
from collections import defaultdict
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

# Set your Azure Blob Storage connection string and container name
# Load environment variables from .env file
load_dotenv()

# Read configurations from environment variables
CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "users")
MAX_USER_SAMPLES = 50  # Number of user directories to sample


def inspect_user_blob_keys(connection_string: str, container_name: str, sample_limit: int):
    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)

    # Schema map structure: { "blob_type": { "key_name": set(data_types) } }
    schema_map = defaultdict(lambda: defaultdict(set))
    processed_users = set()

    print(f"Scanning container '{container_name}/userdata/' (sampling up to {sample_limit} users)...\n")

    # Limit search strictly to blobs starting with 'userdata/'
    blobs = container_client.list_blobs(name_starts_with="userdata/")

    for blob in blobs:
        # Ignore zero-byte files or any init files ending with '_init'
        if blob.size == 0 or blob.name.lower().endswith("_init"):
            continue

        parts = blob.name.split("/")

        # Expected path structure: ["userdata", "{user_id}", "{blob_type}.json"]
        if len(parts) < 3:
            continue  # Skip files directly under 'userdata/' that aren't inside a user folder

        user_id = parts[1]
        blob_filename = "/".join(parts[2:])  # Handles nested paths inside user folder if any
        blob_type = blob_filename.replace(".json", "")

        # Manage user sampling
        if user_id not in processed_users:
            if len(processed_users) >= sample_limit:
                continue  # Skip new users once sample quota is met
            processed_users.add(user_id)

        # Download and extract keys for sampled users
        if user_id in processed_users:
            try:
                blob_client = container_client.get_blob_client(blob.name)
                download_stream = blob_client.download_blob()
                content = download_stream.readall()

                data = json.loads(content)
                extract_keys_from_json(data, schema_map[blob_type])

            except json.JSONDecodeError:
                print(f"⚠️ Skipped non-JSON file: '{blob.name}'")
            except Exception as e:
                print(f"❌ Error reading blob '{blob.name}': {e}")

    # Output detected schema report
    print_schema_report(schema_map)


def extract_keys_from_json(data, key_type_dict):
    """Recursively or top-level extract keys and record inferred python types."""
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for k, v in item.items():
                    key_type_dict[k].add(type(v).__name__)
    elif isinstance(data, dict):
        for k, v in data.items():
            key_type_dict[k].add(type(v).__name__)


def print_schema_report(schema_map):
    """Prints a clean summary of tables, columns, and observed data types."""
    print("=" * 60)
    print("PROPOSED RELATIONAL TABLES & COLUMNS")
    print("=" * 60)

    for table_name, columns in schema_map.items():
        print(f"\n Table: [ {table_name} ]")
        print(f"  └── Foreign Key: user_id (FK -> users.id)")
        print("  └── Detected Columns:")

        for col_name, col_types in columns.items():
            types_str = ", ".join(col_types)
            print(f"      • {col_name:<25} (Types seen: {types_str})")


if __name__ == "__main__":
    inspect_user_blob_keys(
        connection_string=CONNECTION_STRING,
        container_name=CONTAINER_NAME,
        sample_limit=MAX_USER_SAMPLES,
    )