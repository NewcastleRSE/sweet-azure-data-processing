import os
import json
import base64
import urllib.parse
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
import requests

load_dotenv()

# Configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "users"
STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

# Global error log tracker & Concern Specific cache
error_log = []
CONCERN_SPECIFIC_CACHE = {}

def clean_payload(data):
    """Removes keys with None, empty string, or whitespace-only values, preserving 0 and False."""
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

def get_or_create_concern_specific(concern_text, sweet_id):
    """Finds or creates a concernSpecific entry and returns its documentId or id for relation linking."""
    if not concern_text:
        return None
    
    concern_text = str(concern_text).strip()
    if not concern_text:
        return None

    if concern_text in CONCERN_SPECIFIC_CACHE:
        return CONCERN_SPECIFIC_CACHE[concern_text]

    try:
        encoded_concern = urllib.parse.quote(concern_text, safe='')
        search_res = requests.get(f"{STRAPI_URL}/api/concern-specifics?filters[concern][$eq]={encoded_concern}", headers=HEADERS)
        
        if search_res.status_code == 200:
            data = search_res.json().get("data", [])
            if data and len(data) > 0:
                entry_identifier = data[0].get("documentId") or data[0].get("id")
                CONCERN_SPECIFIC_CACHE[concern_text] = entry_identifier
                return entry_identifier

        create_res = requests.post(
            f"{STRAPI_URL}/api/concern-specifics",
            headers=HEADERS,
            json={"data": {"concern": concern_text}}
        )
        if create_res.status_code in [200, 201]:
            created_data = create_res.json().get("data", {})
            entry_identifier = created_data.get("documentId") or created_data.get("id")
            if entry_identifier:
                CONCERN_SPECIFIC_CACHE[concern_text] = entry_identifier
                return entry_identifier
        else:
            error_log.append({
                "sweet_id": sweet_id,
                "endpoint": "concern-specifics",
                "status_code": create_res.status_code,
                "response": create_res.text,
                "payload": {"concern": concern_text}
            })
    except Exception as e:
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": "concern-specifics",
            "status_code": None,
            "response": str(e),
            "payload": {"concern": concern_text}
        })
    
    return None

def get_strapi_user_by_sweet_id(sweet_id):
    try:
        res = requests.get(f"{STRAPI_URL}/api/users?filters[SweetID][$eq]={sweet_id}", headers=HEADERS)
        if res.status_code == 200:
            users = res.json()
            if users and len(users) > 0:
                return users[0].get("id"), users[0].get("documentId")
    except Exception as e:
        print(f"⚠️ Error querying Strapi for SweetID {sweet_id}: {e}")
    return None, None

def update_user_init_date(user_db_id, init_date, sweet_id):
    try:
        res = requests.put(f"{STRAPI_URL}/api/users/{user_db_id}", headers=HEADERS, json={"init": init_date})
        if res.status_code == 200:
            print(f"   ✨ Successfully updated user init date to: {init_date}")
        else:
            err_msg = f"Failed to update user init date: {res.text}"
            print(f"   ⚠️ {err_msg}")
            error_log.append({
                "sweet_id": sweet_id,
                "endpoint": f"users/{user_db_id}",
                "status_code": res.status_code,
                "response": res.text,
                "payload": {"init": init_date}
            })
    except Exception as e:
        err_msg = f"Exception updating user init: {str(e)}"
        print(f"   ❌ {err_msg}")
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": f"users/{user_db_id}",
            "status_code": None,
            "response": err_msg,
            "payload": {"init": init_date}
        })

def post_to_strapi(endpoint, payload, sweet_id):
    try:
        cleaned_data = clean_payload(payload)
        full_payload = {"data": cleaned_data}
        res = requests.post(f"{STRAPI_URL}/api/{endpoint}", headers=HEADERS, json=full_payload)
        if res.status_code in [200, 201]:
            return True
        else:
            err_msg = f"[Error {res.status_code}] {res.text}"
            print(f"   ❌ Failed posting to '{endpoint}': {err_msg}")
            error_log.append({
                "sweet_id": sweet_id,
                "endpoint": endpoint,
                "status_code": res.status_code,
                "response": res.text,
                "payload": full_payload
            })
            return False
    except Exception as e:
        err_msg = f"Exception: {str(e)}"
        print(f"   ❌ Exception posting to '{endpoint}': {err_msg}")
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": endpoint,
            "status_code": None,
            "response": err_msg,
            "payload": payload
        })
        return False

def put_to_strapi(endpoint, entry_id, payload, sweet_id):
    try:
        cleaned_data = clean_payload(payload)
        full_payload = {"data": cleaned_data}
        res = requests.put(f"{STRAPI_URL}/api/{endpoint}/{entry_id}", headers=HEADERS, json=full_payload)
        if res.status_code == 200:
            return True
        else:
            err_msg = f"[Error {res.status_code}] {res.text}"
            print(f"   ❌ Failed updating '{endpoint}/{entry_id}': {err_msg}")
            error_log.append({
                "sweet_id": sweet_id,
                "endpoint": f"{endpoint}/{entry_id}",
                "status_code": res.status_code,
                "response": res.text,
                "payload": full_payload
            })
            return False
    except Exception as e:
        err_msg = f"Exception: {str(e)}"
        print(f"   ❌ Exception updating '{endpoint}/{entry_id}': {err_msg}")
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": f"{endpoint}/{entry_id}",
            "status_code": None,
            "response": err_msg,
            "payload": payload
        })
        return False

def build_query_string(filters):
    """Flattens a nested filters dict/list into Strapi's bracket-notation query params."""
    def _flatten(obj, prefix):
        items = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                items.extend(_flatten(v, f"{prefix}[{k}]" if prefix else k))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                items.extend(_flatten(v, f"{prefix}[{i}]"))
        else:
            items.append((prefix, obj))
        return items
    return _flatten({"filters": filters}, "")

def build_match(**fields):
    """Builds $eq filters from the given fields, skipping any that are blank."""
    match = {}
    for key, value in fields.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        match[key] = {"$eq": value}
    return match

def find_existing_entries(endpoint, user_db_id, match_filters, sweet_id):
    filters = {"user": {"$eq": user_db_id}}
    filters.update(match_filters)
    params = build_query_string(filters) + [("pagination[pageSize]", 100)]
    try:
        res = requests.get(f"{STRAPI_URL}/api/{endpoint}", headers=HEADERS, params=params)
        if res.status_code == 200:
            return res.json().get("data", [])
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": endpoint,
            "status_code": res.status_code,
            "response": res.text,
            "payload": {"filters": match_filters}
        })
    except Exception as e:
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": endpoint,
            "status_code": None,
            "response": str(e),
            "payload": {"filters": match_filters}
        })
    return []

# Fields that should never trigger an update just because they exist on the fetched entry
IGNORED_COMPARISON_KEYS = {"id", "documentId", "createdAt", "updatedAt", "publishedAt", "user", "locale"}

def entries_differ(existing, new_payload):
    for key, value in new_payload.items():
        if key in IGNORED_COMPARISON_KEYS:
            continue
        # Relation payloads (e.g. {"connect": [...]}) aren't returned unpopulated, so skip comparing them
        if isinstance(value, dict):
            continue
        if existing.get(key) != value:
            return True
    return False

def upsert_to_strapi(endpoint, payload, sweet_id, match_filters):
    """Creates a new entry if none matches match_filters, otherwise updates it only if changed."""
    user_db_id = payload.get("user")
    if not match_filters:
        print(f"   ℹ️ No natural key available for '{endpoint}', creating without duplicate check.")
        return post_to_strapi(endpoint, payload, sweet_id)

    existing_entries = find_existing_entries(endpoint, user_db_id, match_filters, sweet_id)
    if len(existing_entries) > 1:
        print(f"   ⚠️ Found {len(existing_entries)} existing '{endpoint}' entries matching {match_filters} (likely duplicates from a previous run) — only the most recent will be updated.")

    if existing_entries:
        target = existing_entries[-1]
        entry_id = target.get("documentId") or target.get("id")
        cleaned = clean_payload(payload)
        if entries_differ(target, cleaned):
            return put_to_strapi(endpoint, entry_id, payload, sweet_id)
        return True

    return post_to_strapi(endpoint, payload, sweet_id)

def process_user_userdata(sweet_id, container_client):
    print(f"\n========================================")
    print(f"🔍 Processing User Data for SweetID: '{sweet_id}'")
    print(f"========================================")

    user_db_id, user_doc_id = get_strapi_user_by_sweet_id(sweet_id)
    if not user_db_id:
        print(f"❌ User with SweetID '{sweet_id}' was not found in Strapi. Skipping userdata.")
        error_log.append({
            "sweet_id": sweet_id,
            "endpoint": "system",
            "status_code": 404,
            "response": "User not found in Strapi database",
            "payload": None
        })
        return

    print(f"✅ Found Strapi User ID: {user_db_id} (DocID: {user_doc_id})")

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
            
            if file_name == "_init":
                init_date = content.strip()
                print(f"   ⏳ Found init date: {init_date}")
                update_user_init_date(user_db_id, init_date, sweet_id)
                continue

            try:
                data = json.loads(content)
            except json.JSONDecodeError as jde:
                print(f"   ❌ JSON Decode Error in '{file_name}': {jde}")
                error_log.append({
                    "sweet_id": sweet_id,
                    "endpoint": file_name,
                    "status_code": None,
                    "response": f"JSON Decode Error: {str(jde)}",
                    "payload": content[:500]
                })
                continue

            if file_name == "contacts":
                if isinstance(data, list):
                    print(f"   📋 Importing {len(data)} contacts...")
                    for contact in data:
                        contact["user"] = user_db_id
                        match = build_match(type=contact.get("type"), name=contact.get("name"))
                        upsert_to_strapi("contacts", contact, sweet_id, match)

            elif file_name == "diary":
                if isinstance(data, dict):
                    print(f"   📅 Processing diary entries across {len(data)} dates...")
                    for date_key, day_content in data.items():
                        if not isinstance(day_content, dict):
                            continue
                        
                        taken_data = day_content.get("taken")
                        updated_data = day_content.get("updated")

                        # Adherence (one entry per date)
                        if "adherence" in day_content:
                            adherence_payload = {"date": date_key, "adherence": day_content["adherence"], "user": user_db_id}
                            upsert_to_strapi("adherences", adherence_payload, sweet_id, build_match(date=date_key))

                        # Side Effects
                        if "sideeffects" in day_content and isinstance(day_content["sideeffects"], list):
                            for se_item in day_content["sideeffects"]:
                                if isinstance(se_item, dict):
                                    se_payload = se_item.copy()
                                    se_payload["date"] = date_key
                                    se_payload["user"] = user_db_id
                                    match = build_match(date=date_key, type=se_item.get("type"))
                                    upsert_to_strapi("side-effects", se_payload, sweet_id, match)

                        # Notes (and pop 'taken' or 'updated' if nested inside notes)
                        if "notes" in day_content and isinstance(day_content["notes"], dict):
                            note_obj = day_content["notes"]
                            if not taken_data and "taken" in note_obj:
                                taken_data = note_obj.pop("taken")
                            if not updated_data and "updated" in note_obj:
                                updated_data = note_obj.pop("updated")
                                
                            note_payload = note_obj.copy()
                            note_payload["date"] = date_key
                            note_payload["user"] = user_db_id
                            upsert_to_strapi("notes", note_payload, sweet_id, build_match(date=date_key))

                        # Merge 'taken'/'updated' into a single 'drugs' record for this date
                        drug_payload = {"user": user_db_id}
                        if isinstance(taken_data, dict):
                            t_date = taken_data.get("date") or date_key
                            t_time = taken_data.get("time")
                            if t_date and t_time:
                                drug_payload["taken"] = f"{t_date}T{format_time_to_hh_mm_ss_sss(t_time)}"

                        if isinstance(updated_data, dict):
                            u_date = updated_data.get("date") or date_key
                            u_time = updated_data.get("time")
                            if u_date and u_time:
                                drug_payload["updated"] = f"{u_date}T{format_time_to_hh_mm_ss_sss(u_time)}"

                        if "taken" in drug_payload or "updated" in drug_payload:
                            # drugs has no 'date' field, so match on the day portion of taken/updated
                            drug_match = {"$or": [
                                {"taken": {"$containsi": date_key}},
                                {"updated": {"$containsi": date_key}},
                            ]}
                            upsert_to_strapi("drugs", drug_payload, sweet_id, drug_match)

            elif file_name == "favourites":
                items = data if isinstance(data, list) else [data]
                print(f"   ⭐ Importing {len(items)} favourites...")
                for fav in items:
                    fav["user"] = user_db_id
                    upsert_to_strapi("favourites", fav, sweet_id, build_match(path=fav.get("path")))

            elif file_name == "meta":
                if isinstance(data, dict):
                    print(f"   ⚙️ Importing meta entries...")
                    for key, value in data.items():
                        if key == "21dayoption":
                            payload = {"twenty_one_day_option": value, "user": user_db_id}
                            upsert_to_strapi("metas", payload, sweet_id, {"type": {"$null": True}})
                        elif isinstance(value, dict):
                            outer_key = key
                            if any(k in value for k in ["y", "p", "n"]):
                                payload = {"type": outer_key, "y": value.get("y", 0), "p": value.get("p", 0), "n": value.get("n", 0), "user": user_db_id}
                                upsert_to_strapi("metas", payload, sweet_id, build_match(type=outer_key))
                            else:
                                for sub_key, sub_val in value.items():
                                    if isinstance(sub_val, dict):
                                        payload = {"type": outer_key, "subtype": sub_key, "y": sub_val.get("y", 0), "p": sub_val.get("p", 0), "n": sub_val.get("n", 0), "user": user_db_id}
                                        upsert_to_strapi("metas", payload, sweet_id, build_match(type=outer_key, subtype=sub_key))

            elif file_name == "plans":
                items = data.values() if isinstance(data, dict) else (data if isinstance(data, list) else [])
                print(f"   🗺️ Importing plans...")
                for plan in items:
                    if isinstance(plan, dict):
                        plan_payload = plan.copy()
                        plan_payload["user"] = user_db_id
                        match = build_match(type=plan.get("type"), time=plan.get("time"))
                        upsert_to_strapi("plans", plan_payload, sweet_id, match)

            elif file_name == "profilers":
                items = data if isinstance(data, list) else [data]
                print(f"   👤 Importing {len(items)} profilers...")
                for profiler in items:
                    if isinstance(profiler, dict):
                        profiler_payload = profiler.copy()
                        
                        concern_specifics_raw = profiler_payload.pop("concernSpecifics", [])
                        specifics_ids = []
                        if isinstance(concern_specifics_raw, list):
                            for concern_text in concern_specifics_raw:
                                if concern_text:
                                    spec_id = get_or_create_concern_specific(concern_text, sweet_id)
                                    if spec_id:
                                        specifics_ids.append(spec_id)

                        # Using the correct 'specifics' relation field on the profiler table
                        if specifics_ids:
                            profiler_payload["specifics"] = {"connect": specifics_ids}

                        profiler_payload["user"] = user_db_id
                        match = build_match(dateComplete=profiler_payload.get("dateComplete"), dueDate=profiler_payload.get("dueDate"))
                        upsert_to_strapi("profilers", profiler_payload, sweet_id, match)

            elif file_name == "reminders":
                if isinstance(data, dict):
                    print(f"   ⏰ Processing reminders by type...")
                    for reminder_type, details in data.items():
                        if isinstance(details, dict) and details.get("reminder") is True:
                            reminder_payload = details.copy()
                            reminder_payload.pop("reminder", None)
                            if "time" in reminder_payload and reminder_payload["time"]:
                                reminder_payload["time"] = format_time_to_hh_mm_ss_sss(reminder_payload["time"])
                            reminder_payload["type"] = reminder_type
                            reminder_payload["user"] = user_db_id
                            upsert_to_strapi("reminders", reminder_payload, sweet_id, build_match(type=reminder_type))

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
                                    match = build_match(path=path_key, negative=thought_payload.get("negative"))
                                    upsert_to_strapi("thoughts", thought_payload, sweet_id, match)

            elif file_name == "goals":
                if isinstance(data, list):
                    print(f"   🎯 Importing {len(data)} goals...")
                    for goal in data:
                        if isinstance(goal, dict):
                            goal_payload = goal.copy()
                            if "status" in goal_payload:
                                goal_payload["goal_status"] = goal_payload.pop("status")
                            goal_payload["user"] = user_db_id
                            match = build_match(goaltype=goal_payload.get("goaltype"), reviewDate=goal_payload.get("reviewDate"))
                            upsert_to_strapi("goals", goal_payload, sweet_id, match)

            else:
                print(f"   ❓ Unhandled file type encountered: '{file_name}'")

        except Exception as file_err:
            err_msg = f"Error reading file '{file_name}': {str(file_err)}"
            print(f"   ❌ {err_msg}")
            error_log.append({
                "sweet_id": sweet_id,
                "endpoint": file_name,
                "status_code": None,
                "response": err_msg,
                "payload": None
            })

    if file_found_count == 0:
        print(f"⚠️ No files found in Azure under 'userdata/{sweet_id}/'")

def run_full_migration():
    try:
        print("☁️ Connecting to Azure Blob Storage for Full Migration...")
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)

        print("🔍 Scanning 'userdata/' to discover all user SweetIDs...")
        blobs = container_client.list_blobs(name_starts_with="userdata/")
        
        all_sweet_ids = set()
        for blob in blobs:
            parts = blob.name.split("/")
            if len(parts) >= 3:
                all_sweet_ids.add(parts[1])

        print(f"🚀 Found {len(all_sweet_ids)} user folders to process.\n")

        for sweet_id in sorted(all_sweet_ids):
            process_user_userdata(sweet_id, container_client)

        print("\n========================================")
        print("✨ Full Userdata Migration Finished!")
        print("========================================")

        if error_log:
            error_filename = "import_user_content_errors.json"
            with open(error_filename, "w", encoding="utf-8") as f:
                json.dump(error_log, f, indent=2)
            print(f" ⚠️ {len(error_log)} errors were encountered and logged to '{error_filename}'.")
        else:
            print(" 🎉 Zero errors encountered! All userdata imported successfully.")
        print("========================================")

    except Exception as e:
        print(f"❌ Critical error during migration execution: {e}")

if __name__ == "__main__":
    run_full_migration()