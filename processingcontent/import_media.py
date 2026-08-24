import json
import os
import io
import requests
from lzstring import LZString
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

load_dotenv()

AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "content"
STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

lz = LZString()
MEDIA_CACHE = {}

IMPORT_LOGS = {
    "successful_pages": [],
    "failed_pages": [],
    "uploaded_media": [],
    "failed_media": [],
    "unhandled_blocks": [],
    "warnings": []
}

VALID_ENDPOINT = None

def discover_strapi_endpoint():
    global VALID_ENDPOINT
    test_endpoints = ["/api/pages", "/api/page"]
    for ep in test_endpoints:
        try:
            res = requests.get(f"{STRAPI_URL}{ep}", headers=HEADERS)
            if res.status_code in [200, 403]:
                VALID_ENDPOINT = ep
                print(f"🔍 Discovered active Strapi endpoint: {VALID_ENDPOINT}")
                return
        except Exception:
            continue
    VALID_ENDPOINT = "/api/pages"
    print(f"⚠️ Defaulting to endpoint: {VALID_ENDPOINT}")


def upload_blob_to_strapi(blob_client, blob_name: str):
    filename = os.path.basename(blob_name)
    if not filename:
        return None
    if filename in MEDIA_CACHE:
        return MEDIA_CACHE[filename]

    try:
        stream = blob_client.download_blob()
        file_bytes = stream.readall()
        file_obj = io.BytesIO(file_bytes)
        files = {'files': (filename, file_obj, 'image/auto')}
        upload_headers = {"Authorization": f"Bearer {STRAPI_API_TOKEN}"}
        
        res = requests.post(f"{STRAPI_URL}/api/upload", headers=upload_headers, files=files)
        if res.status_code in [200, 201]:
            media_data = res.json()
            media_id = media_data[0]['id'] if isinstance(media_data, list) else media_data['data']['id']
            MEDIA_CACHE[filename] = media_id
            IMPORT_LOGS["uploaded_media"].append(filename)
            return media_id
    except Exception as e:
        IMPORT_LOGS["failed_media"].append({"file": filename, "error": str(e)})
    return None


def sync_azure_media_library():
    if not AZURE_CONN_STR:
        return
    print("☁️ Connecting to Azure Blob Storage...")
    try:
        service_client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
        container_client = service_client.get_container_client(CONTAINER_NAME)
        blobs = container_client.list_blobs(name_starts_with="resourceblobs/")
        for blob in blobs:
            if blob.size > 0:
                upload_blob_to_strapi(container_client.get_blob_client(blob.name), blob.name)
        print(f"✨ Mapped {len(MEDIA_CACHE)} images into Strapi.\n")
    except Exception as e:
        print(f"❌ Azure connection error: {e}")


def decode_text(text: str, encoding: str) -> str:
    if not text or not isinstance(text, str):
        return str(text or "")
    if encoding == "plain" or (len(text) < 10 and not text.startswith("M")):
        return text
    try:
        if encoding == "lz-string:B64":
            return lz.decompressFromBase64(text) or text
        elif encoding == "lz-string:UTF16":
            return lz.decompressFromUTF16(text) or text
    except Exception:
        pass
    return text


def extract_quotes_and_body(content_list: list, context_path: str):
    body_text = ""
    quotes = []
    for item in content_list:
        if not isinstance(item, dict):
            body_text += str(item) + "\n\n"
            continue
        itype = item.get("type")
        if itype == "markdown":
            body_text += decode_text(item.get("text", ""), item.get("encoding", "")) + "\n\n"
        elif itype == "popup":
            body_text += f"\n[Popup: {item.get('title', item.get('name'))}]\n\n"
        elif itype == "container":
            for c_item in item.get("content", []):
                if isinstance(c_item, dict) and c_item.get("type") == "block-quote":
                    quotes.append({"text": c_item.get("text", ""), "citation": c_item.get("citation", "")})
    return body_text.strip(), quotes


def transform_block(item: dict, page_route: str):
    if not isinstance(item, dict):
        return {"__component": "blocks.markdown", "text": str(item), "encoding": "plain"}

    item_type = item.get("type")
    if item_type == "markdown":
        return {"__component": "blocks.markdown", "text": decode_text(item.get("text", ""), item.get("encoding", "")), "encoding": "plain"}
    elif item_type in ["menu", "described-menu", "homepage-menu"]:
        menu_items = []
        raw_items = item.get("content", [])
        if "mainitems" in item:
            raw_items = item.get("mainitems", []) + item.get("sideitems", [])
        for mi in raw_items:
            if isinstance(mi, dict):
                menu_items.append({"title": mi.get("title", ""), "link": mi.get("link", ""), "icon": mi.get("icon", "none"), "description": mi.get("description", "")})
        return {"__component": "blocks.menu", "menu_type": item_type, "items": menu_items}
    elif item_type == "accordion":
        acc_items = []
        for acc in item.get("content", []):
            if isinstance(acc, dict):
                body_text, quotes = extract_quotes_and_body(acc.get("content", []), page_route)
                acc_items.append({"header": acc.get("header", ""), "icon": acc.get("icon", "none"), "body": body_text, "quotes": quotes})
        return {"__component": "blocks.accordion", "items": acc_items}
    elif item_type == "popup":
        body_text, quotes = extract_quotes_and_body(item.get("content", []), page_route)
        return {"__component": "blocks.popup", "name_key": item.get("name", ""), "title": item.get("title", ""), "size": item.get("size", "lg") or "lg", "body": body_text, "quotes": quotes}
    elif item_type == "standout":
        inner = item.get("content", [{}])[0] if item.get("content") else {}
        return {"__component": "blocks.standout", "class": item.get("class", "so-important"), "text": decode_text(inner.get("text", ""), inner.get("encoding", ""))}
    elif item_type == "carousel":
        partner_items = []
        for slide in item.get("slides", []):
            if isinstance(slide, dict) and isinstance(slide.get("content"), dict):
                for res_name in slide["content"].get("resources", []):
                    matched_id = next((mid for fname, mid in MEDIA_CACHE.items() if str(res_name).strip().lower() in fname.lower()), None)
                    partner_items.append({"name": str(res_name).strip(), "url": "", "logo": matched_id})
        return {"__component": "blocks.partner-carousel", "name": item.get("name", "Logos"), "partners": partner_items}
    elif item_type in ["goalsetter", "goalchecker", "diary-calendar", "diarygraph", "reminders", "my-plans", "user-details-page", "my-personal-support", "thoughts-page", "favourites-page", "index-list", "thoughts", "contacts-page", "fillin", "plan"]:
        return {"__component": "blocks.interactive-tool", "tool_type": item_type, "config": {k: v for k, v in item.items() if k != "type"}}
    return None


def merge_json_files(content_path, structure_path, resources_path):
    merged_data = {}
    for file_path in [content_path, structure_path, resources_path]:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                file_data = json.load(f)
                for route, blocks in file_data.items():
                    if route not in merged_data:
                        merged_data[route] = []
                    if isinstance(blocks, list):
                        for b in blocks:
                            if b not in merged_data[route]:
                                merged_data[route].append(b)
    return merged_data


def import_all_to_strapi():
    discover_strapi_endpoint()
    sync_azure_media_library()

    merged_routes = merge_json_files("content.json", "structure.json", "resources.json")
    print(f"🚀 Importing {len(merged_routes)} routes cleanly...")

    slug_to_id = {}
    sorted_routes = sorted(merged_routes.keys(), key=lambda r: r.count("/"))

    # ---------------------------------------------------------
    # PASS 1: Create or Update all pages safely (No relations yet)
    # ---------------------------------------------------------
    for raw_route in sorted_routes:
        blocks = merged_routes[raw_route]
        clean_route = raw_route.lstrip("#").strip()
        slug = clean_route.replace("/", "-").lower() or "home"
        title = slug.split("-")[-1].replace("-", " ").title() or "Home"

        dynamic_zone_payload = []
        for block in blocks:
            if isinstance(block, dict):
                if block.get("type") == "container":
                    for inner in block.get("content", []):
                        if isinstance(inner, dict) and inner.get("type") == "block-quote":
                            dynamic_zone_payload.append({"__component": "blocks.quote-block", "quote_details": {"text": inner.get("text", ""), "citation": inner.get("citation", "")}})
                        else:
                            t = transform_block(inner, slug)
                            if t: dynamic_zone_payload.append(t)
                else:
                    t = transform_block(block, slug)
                    if t: dynamic_zone_payload.append(t)

        payload = {
            "data": {
                "title": title,
                "slug": slug,
                "content": dynamic_zone_payload
            }
        }

        try:
            check_res = requests.get(f"{STRAPI_URL}{VALID_ENDPOINT}?filters[slug][$eq]={slug}", headers=HEADERS)
            existing_id = None
            if check_res.status_code == 200:
                data = check_res.json().get("data", [])
                if data:
                    existing_id = data[0].get("documentId") or data[0].get("id")

            if existing_id:
                res = requests.put(f"{STRAPI_URL}{VALID_ENDPOINT}/{existing_id}", headers=HEADERS, json=payload)
                record_id = existing_id
                action = "Updated"
            else:
                res = requests.post(f"{STRAPI_URL}{VALID_ENDPOINT}", headers=HEADERS, json=payload)
                record_id = None
                if res.text:
                    try:
                        res_json = res.json()
                        if res_json:
                            res_data = res_json.get("data", res_json)
                            if isinstance(res_data, dict):
                                record_id = res_data.get("documentId") or res_data.get("id")
                    except Exception:
                        pass
                
                if not record_id and res.status_code in [200, 201]:
                    fallback_res = requests.get(f"{STRAPI_URL}{VALID_ENDPOINT}?filters[slug][$eq]={slug}", headers=HEADERS)
                    if fallback_res.status_code == 200:
                        fb_data = fallback_res.json().get("data", [])
                        if fb_data:
                            record_id = fb_data[0].get("documentId") or fb_data[0].get("id")

                action = "Created"

            if res.status_code in [200, 201] and record_id:
                slug_to_id[slug] = record_id
                print(f"✅ {action} Page: {slug}")
                IMPORT_LOGS["successful_pages"].append(slug)
            else:
                print(f"❌ API Error ({slug}): {res.status_code} - {res.text}")
                IMPORT_LOGS["failed_pages"].append({"slug": slug, "error": res.text})
        except Exception as e:
            print(f"❌ Exception on {slug}: {e}")
            IMPORT_LOGS["failed_pages"].append({"slug": slug, "error": str(e)})

    # ---------------------------------------------------------
    # PASS 2: Link Parents using Strapi's explicit connect syntax
    # ---------------------------------------------------------
    print("\n🔗 Linking page hierarchies safely...")
    linked_count = 0

    for raw_route in sorted_routes:
        clean_route = raw_route.lstrip("#").strip()
        if "/" not in clean_route:
            continue

        child_slug = clean_route.replace("/", "-").lower()
        parent_parts = clean_route.split("/")[:-1]
        parent_slug = "-".join(parent_parts).lower()

        child_id = slug_to_id.get(child_slug)
        parent_id = slug_to_id.get(parent_slug)

        if child_id and parent_id:
            relation_payload = {
                "data": {
                    "parent": {
                        "connect": [parent_id]
                    }
                }
            }
            try:
                rel_res = requests.put(f"{STRAPI_URL}{VALID_ENDPOINT}/{child_id}", headers=HEADERS, json=relation_payload)
                if rel_res.status_code in [200, 201]:
                    linked_count += 1
                    print(f"🔗 Linked '{child_slug}' -> Parent '{parent_slug}'")
            except Exception as e:
                print(f"⚠️ Failed to link '{child_slug}': {e}")

    print(f"\n✨ Migration Complete! Successfully processed pages and established {linked_count} hierarchy links.")

if __name__ == "__main__":
    import_all_to_strapi()