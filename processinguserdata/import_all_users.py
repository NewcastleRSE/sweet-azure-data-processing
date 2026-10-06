import os
import json
import base64
import urllib.parse
from azure.storage.blob import BlobServiceClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import requests

load_dotenv()

# Configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "users"
BLOB_NAME = "users.json"
FERNET_SECRET = os.getenv("FERNET_SECRET")
STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

# In-memory cache to store slug -> documentId mappings during execution and prevent duplicates
TUNNEL_CACHE = {}

def get_default_role_id():
    """Fetches roles from Strapi and returns the ID for 'Authenticated' or defaults to 1."""
    try:
        response = requests.get(f"{STRAPI_URL}/api/users-permissions/roles", headers=HEADERS)
        if response.status_code == 200:
            roles = response.json().get("roles", [])
            for role in roles:
                if role.get("type") == "authenticated" or role.get("name") == "Authenticated":
                    return role.get("id")
            if roles:
                return roles[0].get("id")
    except Exception as e:
        print(f"⚠️ Could not fetch roles automatically: {e}. Defaulting to role ID 1.")
    return 1

def get_or_create_tunnel_document_id(slug):
    """Strips leading '#', checks cache, then checks Strapi for existing slug."""
    if not slug:
        return None

    # Clean the slug by removing a leading '#' if present
    slug = slug.lstrip('#')

    # 1. Check local cache first
    if slug in TUNNEL_CACHE:
        return TUNNEL_CACHE[slug]

    try:
        # 2. URL-encode safely and query Strapi
        encoded_slug = urllib.parse.quote(slug, safe='')
        search_url = f"{STRAPI_URL}/api/tunnels?filters[slug][$eq]={encoded_slug}"
        search_res = requests.get(search_url, headers=HEADERS)
        
        if search_res.status_code == 200:
            data = search_res.json().get("data", [])
            if data and len(data) > 0:
                doc_id = data[0].get("documentId")
                TUNNEL_CACHE[slug] = doc_id
                return doc_id

        # 3. If it doesn't exist, create it
        create_res = requests.post(
            f"{STRAPI_URL}/api/tunnels",
            headers=HEADERS,
            json={"data": {"slug": slug}}
        )
        if create_res.status_code in [200, 201]:
            doc_id = create_res.json().get("data", {}).get("documentId")
            if doc_id:
                TUNNEL_CACHE[slug] = doc_id
                return doc_id
    except Exception as e:
        print(f"   ❌ Error handling tunnel '{slug}': {e}")
    
    return None

def import_all_users():
    error_log = []
    success_count = 0
    fail_count = 0

    try:
        print("☁️ Connecting to Azure Blob Storage...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_client = container_client.get_blob_client(BLOB_NAME)

        print("📥 Downloading users.json from Azure...")
        blob_data = blob_client.download_blob()
        users_content = blob_data.readall().decode("utf-8")
        users_obj = json.loads(users_content)

        total_users = len(users_obj)
        print(f"🚀 Found {total_users} users to process. Starting bulk import...\n")

        # Setup Fernet decryption key once
        key_bytes = FERNET_SECRET.encode("utf-8")
        try:
            f = Fernet(key_bytes)
        except Exception:
            formatted_key = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b'0'))
            f = Fernet(formatted_key)

        role_id = get_default_role_id()

        # Loop through every user entry
        for index, (registration_code, encrypted_string) in enumerate(users_obj.items(), start=1):
            print(f"--------------------------------------------------")
            print(f"[{index}/{total_users}] Processing SweetID: {registration_code}")
            
            try:
                # 1. Decrypt user data
                decrypted_bytes = f.decrypt(encrypted_string.encode("utf-8"))
                user_data = json.loads(decrypted_bytes.decode("utf-8"))
                email = user_data.get("email")

                if not email:
                    raise ValueError("Decrypted user object is missing an email address.")

                # 2. Create the user account first
                user_payload = {
                    "username": email,
                    "email": email,
                    "password": user_data.get("password"),
                    "firstName": user_data.get("firstName"),
                    "lastName": user_data.get("lastName"),
                    "mobile": user_data.get("mobile"),
                    "blocked": user_data.get("blocked", False),
                    "deactivated": user_data.get("deactivated", False),
                    "SweetID": registration_code,
                    "confirmed": True,
                    "role": role_id
                }

                create_res = requests.post(
                    f"{STRAPI_URL}/api/users",
                    headers=HEADERS,
                    json=user_payload
                )

                if create_res.status_code not in [200, 201]:

                    # if the error is password not being 6 characters, make password 'password' and retry, ask users to reset password. Use in staging only.
                    if "password must be at least 6 characters" in json.loads(create_res.text).get("error", {}).get("message", ""):
                        print(f"   ⚠️ Password too short, retrying with default password...")
                        user_payload["password"] = "password"
                        create_res = requests.post(
                            f"{STRAPI_URL}/api/users",
                            headers=HEADERS,
                            json=user_payload
                        )
                        continue


                    error_msg = f"User Creation Failed (Status {create_res.status_code}): {create_res.text}, Payload: {json.dumps(user_payload)}"
                    print(f"   ❌ {error_msg}")
                    error_log.append({
                        "sweet_id": registration_code,
                        "email": email,
                        "step": "user_creation",
                        "error": error_msg
                    })
                    fail_count += 1
                    continue

                created_user = create_res.json()
                user_db_id = created_user.get("id")
                print(f"   ✅ User created successfully (Strapi ID: {user_db_id})")

                # 3. Process and link tunnels
                tunnels_raw = user_data.get("tunnelsComplete", [])
                if tunnels_raw and isinstance(tunnels_raw, list):
                    print(f"   🔗 Linking {len(tunnels_raw)} tunnels...")
                    for slug in tunnels_raw:
                        if slug:
                            tunnel_doc_id = get_or_create_tunnel_document_id(slug)
                            if tunnel_doc_id:
                                tunnel_update_payload = {
                                    "data": {
                                        "users": {
                                            "connect": [user_db_id]
                                        }
                                    }
                                }
                                tunnel_res = requests.put(
                                    f"{STRAPI_URL}/api/tunnels/{tunnel_doc_id}",
                                    headers=HEADERS,
                                    json=tunnel_update_payload
                                )
                                if tunnel_res.status_code != 200:
                                    print(f"      ⚠️ Warning: Failed to link tunnel slug '{slug}': {tunnel_res.text}")

                success_count += 1
                print(f"   ✨ Successfully imported user: {email}")

            except Exception as user_err:
                error_msg = str(user_err)
                print(f"   ❌ Exception encountered for SweetID {registration_code}: {error_msg}")
                error_log.append({
                    "sweet_id": registration_code,
                    "step": "processing_exception",
                    "error": error_msg
                })
                fail_count += 1

        # Save errors to a local JSON file if any occurred
        print("\n========================================")
        print("📊 BULK IMPORT FINISHED")
        print("========================================")
        print(f" ✅ Successful imports: {success_count}")
        print(f" ❌ Failed imports:     {fail_count}")

        if error_log:
            error_filename = "import_errors.json"
            with open(error_filename, "w", encoding="utf-8") as f:
                json.dump(error_log, f, indent=2)
            print(f" ⚠️ Errors have been logged to '{error_filename}' for manual review.")
        else:
            print(" 🎉 All users imported successfully with zero errors!")
        print("========================================")

    except Exception as e:
        print(f"❌ Critical error running bulk import script: {e}")

if __name__ == "__main__":
    import_all_users()