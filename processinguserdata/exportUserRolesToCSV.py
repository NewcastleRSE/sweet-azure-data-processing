import os
import json
import base64
import csv
from azure.storage.blob import BlobServiceClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Configuration (matching your checkroles.py setup)
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "users"
BLOB_NAME = "users.json"
FERNET_SECRET = os.getenv("FERNET_SECRET")

def export_user_roles_to_csv():
    try:
        print("☁️ Connecting to Azure Blob Storage...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_client = container_client.get_blob_client(BLOB_NAME)

        print("📥 Downloading users.json from Azure...")
        blob_data = blob_client.download_blob()
        users_content = blob_data.readall().decode("utf-8")
        users_obj = json.loads(users_content)

        print(f"🔍 Processing {len(users_obj)} total user entries for CSV export...\n")

        # Setup Fernet decryption (using your robust fallback logic)
        key_bytes = FERNET_SECRET.encode("utf-8")
        try:
            f = Fernet(key_bytes)
        except Exception:
            formatted_key = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b'0'))
            f = Fernet(formatted_key)

        output_file_name = "users_and_roles_export.csv"
        failed_decryptions = 0
        success_count = 0

        # Open CSV file and write rows using Python's built-in csv module
        with open(output_file_name, mode='w', newline='', encoding='utf-8') as csv_file:
            fieldnames = ['RegistrationCode', 'ID', 'Name', 'Email', 'Role']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            
            writer.writeheader()

            for registration_code, encrypted_string in users_obj.items():
                try:
                    decrypted_bytes = f.decrypt(encrypted_string.encode("utf-8"))
                    user_data = json.loads(decrypted_bytes.decode("utf-8"))
                    
                    # Extract standard fields safely
                    user_id = user_data.get("id") or user_data.get("documentId") or ""
                    name = user_data.get("name") or user_data.get("fullName") or f"{user_data.get('firstName', '')} {user_data.get('lastName', '')}".strip()
                    email = user_data.get("email", "")
                    role = user_data.get("role", "UNKNOWN")

                    writer.writerow({
                        'RegistrationCode': registration_code,
                        'ID': str(user_id),
                        'Name': str(name),
                        'Email': str(email),
                        'Role': str(role)
                    })
                    success_count += 1
                    
                except Exception as e:
                    failed_decryptions += 1

        print("========================================")
        print(f"🎯 [SUCCESS] Exported {success_count} user records to {output_file_name}")
        if failed_decryptions > 0:
            print(f"⚠️ Warning: {failed_decryptions} records failed to decrypt.")
        print("========================================")

    except Exception as e:
        print(f"❌ Error exporting user roles: {e}")

if __name__ == "__main__":
    export_user_roles_to_csv()