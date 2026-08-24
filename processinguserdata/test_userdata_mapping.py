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

def clean_payload(data):
    """Removes keys with None, empty string, or whitespace-only values, but preserves 0 and False."""
    if isinstance(data, dict):
        return {
            k: clean_payload(v) for k, v in data.items() 
            if v is not None and v != "" and (not isinstance(v, str) or v.strip() != "")
        }
    elif isinstance(data, list):
        return [clean_payload(item) for item in data if item is not None and item != ""]
    return data

def format_time_to_hh_mm_ss_sss(time_str):
    """Formats a time string into HH:mm:ss.SSS"""
    if not time_str:
        return None
    try:
        parts = str(time_str).split('.')
        main_time = parts[0]
        ms = parts[1] if len(parts) > 1 else "000"
        
        time_parts = main_time.split(':')
        if len(time_parts) >= 2:
            h, m = int(time_parts[0]), int(time_parts[1])
            s = int(time_parts[2]) if len(time_parts) > 2 else 0
            ms = ms.ljust(3, '0')[:3]
            return f"{h:02d}:{m:02d}:{s:02d}.{ms}"
    except Exception:
        pass
    return time_str

def get_strapi_user_by_sweet_id(sweet_id):
    """Finds a user in Strapi by their SweetID and returns their internal ID and documentId."""
    try:
        res = requests.get(f"{STRAPI_URL}/api/users?filters[SweetID][$eq]={sweet_id}", headers=HEADERS)
        if res.status_code == 200:
            users = res.json()
            if users and len(users) > 0:
                return users[0].get("id"), users[0].get("documentId")
    except Exception as e:
        print(f"⚠️ Error querying Strapi for SweetID {sweet_id}: {e}")
    return None, None

def update_user_init_date(user_db_id, init_date):
    """Updates the 'init' field on the user table."""
    try:
        res = requests.put(f"{STRAPI_URL}/api/users/{user_db_id}", headers=HEADERS, json={"init": init_date})
        if res.status_code == 200:
            print(f"   ✨ Successfully updated user init date to: {init_date}")
        else:
            print(f"   ⚠️ Failed to update user init date (Status {res.status_code}): {res.text}")
    except Exception as e:
        print(f"   ❌ Exception updating user init: {e}")

def post_to_strapi(endpoint, payload):
    """Helper to post cleaned data to a Strapi collection and log payloads on error."""
    try:
        cleaned_data = clean_payload(payload)
        full_payload = {"data": cleaned_data}
        
        res = requests.post(f"{STRAPI_URL}/api/{endpoint}", headers=HEADERS, json=full_payload)
        
        if res.status_code in [200, 201]:
            return True
        else:
            print(f"   ❌ [Error {res.status_code}] Failed posting to '{endpoint}': {res.text}")
            print(f"      📦 [Offending Payload]: {json.dumps(full_payload, indent=2)}")
            return False
    except Exception as e:
        print(f"   ❌ Exception posting to '{endpoint}': {e}")
        print(f"      📦 [Offending Payload]: {json.dumps(payload, indent=2)}")
        return False

def process_user_userdata(sweet_id, container_client):
    print(f"\n========================================")
    print(f"🔍 Processing User Data for SweetID: '{sweet_id}'")
    print(f"========================================")

    # 1. Get Strapi user ID and documentId
    user_db_id, user_doc_id = get_strapi_user_by_sweet_id(sweet_id)
    if not user_db_id:
        print(f"❌ User with SweetID '{sweet_id}' was not found in Strapi. Please run user import first.")
        return

    print(f"✅ Found Strapi User ID: {user_db_id} (DocID: {user_doc_id})")

    # 2. List all files under userdata/{sweet_id}/
    prefix = f"userdata/{sweet_id}/"
    blobs = container_client.list_blobs(name_starts_with=prefix)
    
    file_found_count = 0
    for blob in blobs:
        file_name = blob.name.replace(prefix, "")
        if not file_name:
            continue
        
        file_found_count += 1
        print(f"\n📂 Processing file: '{file_name}'")
        
        try:
            blob_client = container_client.get_blob_client(blob.name)
            content = blob_client.download_blob().readall().decode("utf-8")
            
            # --- _INIT FILE ---
            if file_name == "_init":
                init_date = content.strip()
                print(f"   ⏳ Found init date: {init_date}")
                update_user_init_date(user_db_id, init_date)
                continue

            # Parse JSON content for other files
            try:
                data = json.loads(content)
            except json.JSONDecodeError as jde:
                print(f"   ❌ JSON Decode Error in '{file_name}': {jde}")
                continue

            # --- CONTACTS ---
            if file_name == "contacts":
                if isinstance(data, list):
                    print(f"   📋 Importing {len(data)} contacts...")
                    for contact in data:
                        contact["user"] = user_db_id
                        post_to_strapi("contacts", contact)
                else:
                    print(f"   ⚠️ Unhandled format in 'contacts': expected list, got {type(data)}")

            # --- DIARY ---
            elif file_name == "diary":
                if isinstance(data, dict):
                    print(f"   📅 Processing diary entries across {len(data)} dates...")
                    for date_key, day_content in data.items():
                        if not isinstance(day_content, dict):
                            continue
                        
                        taken_data = day_content.get("taken")

                        # Adherence
                        if "adherence" in day_content:
                            adh_val = day_content["adherence"]
                            adh_payload = {
                                "date": date_key,
                                "adherence": adh_val,
                                "user": user_db_id
                            }
                            post_to_strapi("adherences", adh_payload)

                        # Side Effects
                        if "sideeffects" in day_content:
                            se_list = day_content["sideeffects"]
                            if isinstance(se_list, list):
                                for se_item in se_list:
                                    if isinstance(se_item, dict):
                                        se_payload = se_item.copy()
                                        se_payload["date"] = date_key
                                        se_payload["user"] = user_db_id
                                        post_to_strapi("side-effects", se_payload)

                        # Notes
                        if "notes" in day_content:
                            note_obj = day_content["notes"]
                            if isinstance(note_obj, dict):
                                if not taken_data and "taken" in note_obj:
                                    taken_data = note_obj.pop("taken")
                                
                                note_payload = note_obj.copy()
                                note_payload["date"] = date_key
                                note_payload["user"] = user_db_id
                                post_to_strapi("notes", note_payload)

                        # Process 'taken' into the 'drugs' table using the 'taken' field
                        if isinstance(taken_data, dict):
                            t_date = taken_data.get("date") or date_key
                            t_time = taken_data.get("time")
                            if t_date and t_time:
                                formatted_t_time = format_time_to_hh_mm_ss_sss(t_time)
                                datetime_str = f"{t_date}T{formatted_t_time}"

                                drug_payload = {
                                    "taken": datetime_str,
                                    "user": user_db_id
                                }
                                post_to_strapi("drugs", drug_payload)
                else:
                    print(f"   ⚠️ Unhandled format in 'diary': expected dict, got {type(data)}")

            # --- FAVOURITES ---
            elif file_name == "favourites":
                items = data if isinstance(data, list) else [data]
                print(f"   ⭐ Importing {len(items)} favourites...")
                for fav in items:
                    fav["user"] = user_db_id
                    post_to_strapi("favourites", fav)

            # --- META ---
            elif file_name == "meta":
                if isinstance(data, dict):
                    print(f"   ⚙️ Importing meta entries...")
                    for key, value in data.items():
                        if key == "21dayoption":
                            meta_payload = {
                                "twenty_one_day_option": value,
                                "user": user_db_id
                            }
                            post_to_strapi("metas", meta_payload)
                        elif isinstance(value, dict):
                            outer_key = key  # e.g., 'goalmsg'
                            
                            # Check if value contains 'y', 'p', 'n' directly (No subkey present)
                            if any(k in value for k in ["y", "p", "n"]):
                                meta_payload = {
                                    "type": outer_key,
                                    "y": value.get("y", 0),
                                    "p": value.get("p", 0),
                                    "n": value.get("n", 0),
                                    "user": user_db_id
                                }
                                post_to_strapi("metas", meta_payload)
                            else:
                                # Has subkeys (e.g., 'activity', 'eating')
                                for sub_key, sub_val in value.items():
                                    if isinstance(sub_val, dict):
                                        meta_payload = {
                                            "type": outer_key,
                                            "subtype": sub_key,
                                            "y": sub_val.get("y", 0),
                                            "p": sub_val.get("p", 0),
                                            "n": sub_val.get("n", 0),
                                            "user": user_db_id
                                        }
                                        post_to_strapi("metas", meta_payload)
                else:
                    print(f"   ⚠️ Unhandled structure in 'meta': {data}")

            # --- PLANS ---
            elif file_name == "plans":
                if isinstance(data, dict):
                    print(f"   🗺️ Importing plans from dictionary values...")
                    for plan_key, plan_obj in data.items():
                        if isinstance(plan_obj, dict):
                            plan_payload = plan_obj.copy()
                            plan_payload["user"] = user_db_id
                            post_to_strapi("plans", plan_payload)
                elif isinstance(data, list):
                    print(f"   🗺️ Importing {len(data)} plans...")
                    for plan in data:
                        if isinstance(plan, dict):
                            plan_payload = plan.copy()
                            plan_payload["user"] = user_db_id
                            post_to_strapi("plans", plan_payload)
                else:
                    print(f"   ⚠️ Unhandled format in 'plans': {type(data)}")

            # --- PROFILERS ---
            elif file_name == "profilers":
                items = data if isinstance(data, list) else [data]
                print(f"   👤 Importing {len(items)} profilers...")
                for profiler in items:
                    profiler["user"] = user_db_id
                    post_to_strapi("profilers", profiler)

            # --- REMINDERS ---
            elif file_name == "reminders":
                if isinstance(data, dict):
                    print(f"   ⏰ Processing reminders by type...")
                    for reminder_type, details in data.items():
                        if isinstance(details, dict):
                            if details.get("reminder") is True:
                                reminder_payload = details.copy()
                                # Remove the 'reminder' field
                                reminder_payload.pop("reminder", None)
                                
                                # Format time field to HH:mm:ss.SSS if present
                                if "time" in reminder_payload and reminder_payload["time"]:
                                    reminder_payload["time"] = format_time_to_hh_mm_ss_sss(reminder_payload["time"])

                                reminder_payload["type"] = reminder_type
                                reminder_payload["user"] = user_db_id
                                post_to_strapi("reminders", reminder_payload)
                else:
                    print(f"   ⚠️ Unhandled format in 'reminders': expected dict, got {type(data)}")

            # --- THOUGHTS ---
            elif file_name == "thoughts":
                if isinstance(data, dict):
                    print(f"   💭 Importing thoughts paths...")
                    for path_key, thought_list in data.items():
                        if isinstance(thought_list, list):
                            for thought_obj in thought_list:
                                if isinstance(thought_obj, dict):
                                    thought_payload = thought_obj.copy()
                                    thought_payload["path"] = path_key
                                    thought_payload["user"] = user_db_id
                                    post_to_strapi("thoughts", thought_payload)
                else:
                    print(f"   ⚠️ Unhandled format in 'thoughts': expected dict, got {type(data)}")

            # --- GOALS ---
            elif file_name == "goals":
                if isinstance(data, list):
                    print(f"   🎯 Importing {len(data)} goals...")
                    for goal in data:
                        goal["user"] = user_db_id
                        post_to_strapi("goals", goal)
                else:
                    print(f"   ⚠️ Unhandled format in 'goals': expected list, got {type(data)}")

            else:
                print(f"   ❓ Unhandled file type encountered: '{file_name}' (Needs manual mapping)")

        except Exception as file_err:
            print(f"   ❌ Error reading file '{file_name}': {file_err}")

    if file_found_count == 0:
        print(f"⚠️ No files found in Azure under 'userdata/{sweet_id}/'")

def run_mapping_test():
    try:
        print("☁️ Connecting to Azure Blob Storage...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        print("🔍 Scanning 'userdata/' to identify the richest user...")
        blobs = container_client.list_blobs(name_starts_with="userdata/")
        user_file_counts = {}
        for blob in blobs:
            parts = blob.name.split("/")
            if len(parts) >= 3:
                sweet_id = parts[1]
                user_file_counts[sweet_id] = user_file_counts.get(sweet_id, 0) + 1

        richest_sweet_id = max(user_file_counts, key=user_file_counts.get) if user_file_counts else None
        
        target_users = []
        if richest_sweet_id:
            print(f"🎯 Auto-identified Richest User SweetID: '{richest_sweet_id}' ({user_file_counts[richest_sweet_id]} files)")
            target_users.append(richest_sweet_id)
        
        if "k.court" not in target_users:
            target_users.append("k.court")

        for sweet_id in target_users:
            process_user_userdata(sweet_id, container_client)

        print("\n========================================")
        print("✨ Userdata Mapping Diagnostic Complete!")
        print("========================================")

    except Exception as e:
        print(f"❌ Critical error during test execution: {e}")

if __name__ == "__main__":
    run_mapping_test()