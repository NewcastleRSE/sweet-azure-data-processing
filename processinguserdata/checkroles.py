import os
import json
import base64
from azure.storage.blob import BlobServiceClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "users"
BLOB_NAME = "users.json"
FERNET_SECRET = os.getenv("FERNET_SECRET")

def scan_user_roles():
    try:
        print("☁️ Connecting to Azure Blob Storage...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_client = container_client.get_blob_client(BLOB_NAME)

        print("📥 Downloading users.json from Azure...")
        blob_data = blob_client.download_blob()
        users_content = blob_data.readall().decode("utf-8")
        users_obj = json.loads(users_content)

        print(f"🔍 Scanning {len(users_obj)} total user entries for unique roles...\n")

        # Setup Fernet decryption
        key_bytes = FERNET_SECRET.encode("utf-8")
        try:
            f = Fernet(key_bytes)
        except Exception:
            formatted_key = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b'0'))
            f = Fernet(formatted_key)

        unique_roles = set()
        role_counts = {}
        failed_decryptions = 0

        for registration_code, encrypted_string in users_obj.items():
            try:
                decrypted_bytes = f.decrypt(encrypted_string.encode("utf-8"))
                user_data = json.loads(decrypted_bytes.decode("utf-8"))
                
                role = user_data.get("role", "UNKNOWN")
                unique_roles.add(role)
                
                # Keep a tally of how many users have each role
                role_counts[role] = role_counts.get(role, 0) + 1
            except Exception as e:
                failed_decryptions += 1

        print("========================================")
        print("🎯 UNIQUE ROLES FOUND IN users.json:")
        print("========================================")
        for role in sorted(unique_roles, key=str):
            count = role_counts[role]
            print(f" • Role: '{role}' (Found in {count} user records)")
        
        if failed_decryptions > 0:
            print(f"\n⚠️ Warning: {failed_decryptions} records failed to decrypt.")
        print("========================================")

    except Exception as e:
        print(f"❌ Error scanning roles: {e}")

if __name__ == "__main__":
    scan_user_roles()