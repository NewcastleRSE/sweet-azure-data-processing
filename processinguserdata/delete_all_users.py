import os
import requests
from dotenv import load_dotenv

load_dotenv()

STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

def delete_all_users():
    print("🔍 Fetching all users from Strapi...")
    response = requests.get(f"{STRAPI_URL}/api/users", headers=HEADERS)

    if response.status_code != 200:
        print(f"❌ Failed to fetch users. Status: {response.status_code}, Response: {response.text}")
        return

    users = response.json()
    print(f"📋 Found {len(users)} users in the database.")

    if not users:
        print("✨ No users to delete.")
        return

    deleted_count = 0
    for user in users:
        user_id = user.get("id")
        email = user.get("email")

        # Safety check: skip deleting your admin email if you know it
        if email == "admin@example.com":  # Change this to your admin email if needed
            print(f"🛡️ Skipping admin account: {email}")
            continue

        del_res = requests.delete(f"{STRAPI_URL}/api/users/{user_id}", headers=HEADERS)
        if del_res.status_code in [200, 204]:
            print(f"   ❌ Deleted user: {email} (ID: {user_id})")
            deleted_count += 1
        else:
            print(f"   ⚠️ Failed to delete user {email}: {del_res.text}")

    print("========================================")
    print(f"🎉 Successfully deleted {deleted_count} users!")
    print("========================================")

if __name__ == "__main__":
    delete_all_users()