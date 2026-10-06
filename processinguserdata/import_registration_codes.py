import os
import re
import json
import requests
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv

load_dotenv()

AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "users"
BLOB_NAME = "user-reg-codes.json"

STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

error_log = []

def extract_codes(raw_text):
    """Pulls out every quoted value regardless of the surrounding (non-strict-JSON) wrapper."""
    return re.findall(r'"([^"]+)"', raw_text)

def code_exists(code):
    res = requests.get(
        f"{STRAPI_URL}/api/registration-codes",
        headers=HEADERS,
        params={"filters[code][$eq]": code}
    )
    res.raise_for_status()
    return len(res.json().get("data", [])) > 0

def create_code(code):
    res = requests.post(
        f"{STRAPI_URL}/api/registration-codes",
        headers=HEADERS,
        json={"data": {"code": code}}
    )
    if res.status_code in (200, 201):
        return True
    error_log.append({"code": code, "status_code": res.status_code, "response": res.text})
    return False

def import_registration_codes():
    print(f"☁️ Downloading '{BLOB_NAME}' from Azure Blob Storage...")
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(CONTAINER_NAME)
    content = container_client.get_blob_client(BLOB_NAME).download_blob().readall().decode("utf-8")

    codes = extract_codes(content)
    print(f"🔍 Found {len(codes)} registration codes in the file.")

    created, skipped = 0, 0
    for code in codes:
        code = code.strip()
        if not code:
            continue
        try:
            if code_exists(code):
                print(f"   ⏭️ '{code}' already exists, skipping.")
                skipped += 1
                continue
            if create_code(code):
                print(f"   ✅ Created registration code '{code}'.")
                created += 1
        except Exception as e:
            error_log.append({"code": code, "status_code": None, "response": str(e)})
            print(f"   ❌ Error processing '{code}': {e}")

    print("\n========================================")
    print(f"✨ Finished. Created: {created}, Skipped (already existed): {skipped}, Errors: {len(error_log)}")
    print("========================================")

    if error_log:
        with open("import_registration_codes_errors.json", "w", encoding="utf-8") as f:
            json.dump(error_log, f, indent=2)
        print("⚠️ Errors were logged to 'import_registration_codes_errors.json'.")

if __name__ == "__main__":
    import_registration_codes()
