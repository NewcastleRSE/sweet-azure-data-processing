import os
import json
import base64
import urllib.parse
from azure.storage.blob import BlobServiceClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "users"
BLOB_NAME = "users.json"
FERNET_SECRET = os.getenv("FERNET_SECRET")

def analyze_richest_user():
    try:
        print("☁️ Connecting to Azure Blob Storage...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        # 1. Download users.json to match SweetIDs
        print("📥 Downloading users.json...")
        blob_client = container_client.get_blob_client(BLOB_NAME)
        users_content = blob_client.download_blob().readall().decode("utf-8")
        users_obj = json.loads(users_content)

        # Setup Fernet decryption
        key_bytes = FERNET_SECRET.encode("utf-8")
        try:
            f = Fernet(key_bytes)
        except Exception:
            formatted_key = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b'0'))
            f = Fernet(formatted_key)

        # 2. List all blobs in the 'userdata/' prefix to find user subfolders
        print("🔍 Scanning 'userdata/' folder structure in Azure...")
        blobs = container_client.list_blobs(name_starts_with="userdata/")
        
        user_file_map = {}
        for blob in blobs:
            parts = blob.name.split("/")
            if len(parts) >= 3:  # Expected: ['userdata', SweetID, filename]
                sweet_id = parts[1]
                filename = parts[2]
                if sweet_id not in user_file_map:
                    user_file_map[sweet_id] = []
                user_file_map[sweet_id].append((filename, blob.name))

        if not user_file_map:
            print("❌ No userdata folders found in Azure matching 'userdata/{SweetID}/'.")
            return

        # 3. Find the user with the most files/richest data
        richest_sweet_id = max(user_file_map, key=lambda k: len(user_file_map[k]))
        files_found = user_file_map[richest_sweet_id]
        
        print(f"\n🎯 Selected Richest User SweetID: '{richest_sweet_id}'")
        print(f"📁 Found {len(files_found)} files in their folder:\n")

        # 4. Decrypt their main user record from users.json if available
        user_account_data = {}
        if richest_sweet_id in users_obj:
            try:
                decrypted_bytes = f.decrypt(users_obj[richest_sweet_id].encode("utf-8"))
                user_account_data = json.loads(decrypted_bytes.decode("utf-8"))
                print(f"✅ Successfully decrypted main user record for {user_account_data.get('email')}")
            except Exception as e:
                print(f"⚠️ Could not decrypt main user record: {e}")
        else:
            print(f"⚠️ SweetID '{richest_sweet_id}' was found in userdata/ but not in users.json.")

        print("\n----------------------------------------")
        print("📄 USER FILE CONTENTS & STRUCTURE ANALYSIS:")
        print("----------------------------------------")

        # 5. Download and inspect the content of each file in their folder
        for filename, blob_path in files_found:
            print(f"\n📂 File: '{filename}' (Path: {blob_path})")
            try:
                file_client = container_client.get_blob_client(blob_path)
                content = file_client.download_blob().readall().decode("utf-8")
                
                # Try parsing as JSON if it looks like json or ends with json/txt
                try:
                    parsed_content = json.loads(content)
                    print(json.dumps(parsed_content, indent=2))
                except json.JSONDecodeError:
                    # Raw text (like the _init file containing a date)
                    print(f"   [Raw Text Content]: {content.strip()}")
            except Exception as file_err:
                print(f"   ❌ Error reading file: {file_err}")

        print("\n----------------------------------------")
        print("🛠️ STRUCTURAL MAPPING CHECKLIST FOR YOU:")
        print("----------------------------------------")
        print("1. **_init file**: Contains the date string to be mapped to the user's `init` field.")
        print("2. **Other files (e.g., contacts, etc.)**: Need to be mapped to their corresponding Strapi collections.")
        print("3. **Relational Link**: Every record created from these files must link back to the user via their `SweetID` (or Strapi document ID).")
        print("\nPlease review the output above and tell me:")
        print("  • What are the exact names of the files you see?")
        print("  • What are the exact names of the corresponding Strapi collections/fields?")
        print("  • Are there any nested structures or fields that need restructuring?")
        print("----------------------------------------")

    except Exception as e:
        print(f"❌ Error during diagnostic execution: {e}")

if __name__ == "__main__":
    analyze_richest_user()