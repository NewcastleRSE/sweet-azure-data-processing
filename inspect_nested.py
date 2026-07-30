import re
import json
import os
from collections import defaultdict
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME", "users")
MAX_USER_SAMPLES = 5

# Regex to detect date keys (YYYY-MM-DD) or tag/path keys (#path/to/thing)
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PATH_PATTERN = re.compile(r"^#.*")


def normalize_key(key: str) -> str:
    """Replaces dynamic keys (like dates or hashtag paths) with place-holders for clean schema grouping."""
    if DATE_PATTERN.match(key):
        return "{DATE}"
    elif PATH_PATTERN.match(key):
        return "{PATH}"
    return key


def analyze_deep_nested_structures(connection_string: str, container_name: str, sample_limit: int):
    if not connection_string:
        raise ValueError("Missing AZURE_STORAGE_CONNECTION_STRING in environment or .env file.")

    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)

    # Schema map: { blob_type: { full_path: { sub_key: set(types) } } }
    deep_schema = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    processed_users = set()

    print(f"Scanning container '{container_name}/userdata/' for deeply nested dicts & arrays...\n")

    blobs = container_client.list_blobs(name_starts_with="userdata/")

    for blob in blobs:
        if blob.size == 0 or blob.name.lower().endswith("_init"):
            continue

        parts = blob.name.split("/")
        if len(parts) < 3:
            continue

        user_id = parts[1]
        blob_filename = "/".join(parts[2:])
        blob_type = blob_filename.replace(".json", "")

        if user_id not in processed_users:
            if len(processed_users) >= sample_limit:
                continue
            processed_users.add(user_id)

        if user_id in processed_users:
            try:
                blob_client = container_client.get_blob_client(blob.name)
                download_stream = blob_client.download_blob()
                data = json.loads(download_stream.readall())

                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            walk_json_tree(item, deep_schema[blob_type])
                elif isinstance(data, dict):
                    walk_json_tree(data, deep_schema[blob_type])

            except json.JSONDecodeError:
                pass
            except Exception as e:
                print(f"❌ Error reading blob '{blob.name}': {e}")

    print_deep_report(deep_schema)


def walk_json_tree(data, table_schema, path=""):
    """Recursively traverses dicts and lists to any depth, recording paths and values."""
    if isinstance(data, dict):
        for raw_k, v in data.items():
            k = normalize_key(raw_k)
            current_path = f"{path}.{k}" if path else k
            
            val_type = type(v).__name__
            
            if isinstance(v, dict):
                # Record that this path contains a dict
                table_schema[current_path]["[Type]"].add("dict (nested object)")
                walk_json_tree(v, table_schema, current_path)
            elif isinstance(v, list):
                table_schema[current_path]["[Type]"].add("list (array)")
                walk_json_tree(v, table_schema, f"{current_path}[]")
            else:
                table_schema[path or "root"][k].add(val_type)

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                walk_json_tree(item, table_schema, path)
            elif isinstance(item, list):
                walk_json_tree(item, table_schema, f"{path}[]")
            else:
                elem_type = type(item).__name__
                table_schema[path]["[Primitive Array Values]"].add(elem_type)


def print_deep_report(deep_schema):
    """Prints a clean, fully recursive tree of all nested paths."""
    print("=" * 75)
    print("DEEP NESTED SCHEMA REPORT (UNPACKED TO ALL LEVELS)")
    print("=" * 75)

    for table_name, paths in deep_schema.items():
        print(f"\n Table / Blob Type: [ {table_name} ]")
        print(" " + "-" * 70)

        # Sort paths by depth so parent paths print before children
        sorted_paths = sorted(paths.keys())

        for path in sorted_paths:
            keys_info = paths[path]
            
            # Print path header
            print(f"  📍 Location Path: {path}")

            for field_name, types_seen in keys_info.items():
                types_str = ", ".join(types_seen)
                print(f"      └── • {field_name:<28} (Types: {types_str})")
        print()


if __name__ == "__main__":
    analyze_deep_nested_structures(
        connection_string=CONNECTION_STRING,
        container_name=CONTAINER_NAME,
        sample_limit=MAX_USER_SAMPLES,
    )