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

# In-memory cache to store slug -> documentId mappings during execution
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
                print(f"   ✨ [Found Existing] Tunnel for slug '{slug}' already exists (ID: {doc_id})")
                return doc_id

        # 3. If it doesn't exist, create it with the cleaned slug
        print(f"   ➕ [Creating] Tunnel not found. Creating new tunnel for slug '{slug}'...")
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

def test_single_user_import():
    try:
        print("☁️ Connecting to Azure Blob Storage...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        blob_client = container_client.get_blob_client(BLOB_NAME)

        print("📥 Downloading users.json from Azure...")
        blob_data = blob_client.download_blob()
        users_content = blob_data.readall().decode("utf-8")
        users_obj = json.loads(users_content)

        # Grab first user for testing
        user_items = list(users_obj.items())
        if not user_items:
            print("❌ No users found in users.json")
            return

        registration_code, encrypted_string = user_items[0]
        print(f"\n🔍 Testing with User Registration Code (SweetID): {registration_code}")

        # Decrypt Fernet string
        key_bytes = FERNET_SECRET.encode("utf-8")
        try:
            f = Fernet(key_bytes)
        except Exception:
            formatted_key = base64.urlsafe_b64encode(key_bytes[:32].ljust(32, b'0'))
            f = Fernet(formatted_key)

        decrypted_bytes = f.decrypt(encrypted_string.encode("utf-8"))
        user_data = json.loads(decrypted_bytes.decode("utf-8"))

        role_id = get_default_role_id()
        email = user_data.get("email")
        tunnels_raw = user_data.get("tunnelsComplete", [])

        # 1. Create the user account first
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

        print("\n💾 Step 1: Creating user record in Strapi...")
        create_res = requests.post(
            f"{STRAPI_URL}/api/users",
            headers=HEADERS,
            json=user_payload
        )

        if create_res.status_code not in [200, 201]:
            print(f"❌ Failed to create user: {create_res.text}")
            return

        created_user = create_res.json()
        user_db_id = created_user.get("id")
        print(f"✅ User created successfully! Strapi User ID: {user_db_id}")

        # 2. Step Two: Process tunnels and link user using the 'user' relation field
        if tunnels_raw:
            print(f"\n🔗 Step 2: Processing and linking {len(tunnels_raw)} tunnels...")
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
                        
                        if tunnel_res.status_code == 200:
                            print(f"   ✨ Successfully linked user {user_db_id} to tunnel doc ID {tunnel_doc_id}")
                        else:
                            print(f"   ⚠️ Failed to link tunnel doc ID {tunnel_doc_id}: {tunnel_res.text}")
        else:
            print("ℹ️ No tunnels to link for this user.")

    except Exception as e:
        print(f"❌ Exception during test import: {e}")

if __name__ == "__main__":
    test_single_user_import()