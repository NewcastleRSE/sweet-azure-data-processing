import json
import os
import io
import requests
from lzstring import LZString
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

load_dotenv()

AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER_NAME = "content"  # Container holding your resourceblobs folder
STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}"
}

lz = LZString()
MEDIA_CACHE = {}  # Maps filename -> Strapi Media ID

IMPORT_LOGS = {
    "successful_pages": [],
    "failed_pages": [],
    "uploaded_media": [],
    "failed_media": [],
    "unhandled_blocks": [],
    "warnings": []
}


def upload_blob_to_strapi(blob_client, blob_name: str):
    """Downloads a blob from Azure and uploads it directly to Strapi Media Library."""
    filename = os.path.basename(blob_name)
    if not filename:
        return None

    if filename in MEDIA_CACHE:
        return MEDIA_CACHE[filename]

    try:
        stream = blob_client.download_blob()
        file_bytes = stream.readall()
        file_obj = io.BytesIO(file_bytes)

        files = {
            'files': (filename, file_obj, 'image/auto')
        }
        
        upload_headers = {
            "Authorization": f"Bearer {STRAPI_API_TOKEN}"
        }
        
        res = requests.post(f"{STRAPI_URL}/api/upload", headers=upload_headers, files=files)
        
        if res.status_code in [200, 201]:
            media_data = res.json()
            media_id = media_data[0]['id'] if isinstance(media_data, list) else media_data['data']['id']
            MEDIA_CACHE[filename] = media_id
            IMPORT_LOGS["uploaded_media"].append(filename)
            print(f"🖼️ Uploaded Media: {filename} (ID: {media_id})")
            return media_id
        else:
            IMPORT_LOGS["failed_media"].append({"file": filename, "error": res.text})
            print(f"❌ Failed to upload media '{filename}': {res.status_code} - {res.text}")
            return None
    except Exception as e:
        IMPORT_LOGS["failed_media"].append({"file": filename, "error": str(e)})
        print(f"❌ Exception uploading media '{filename}': {e}")
        return None


def sync_azure_media_library():
    """Connects to Azure Blob Storage and syncs all images from the 'resourceblobs/' folder."""
    if not AZURE_CONN_STR:
        IMPORT_LOGS["warnings"].append("Missing Azure Connection String. Skipping media sync.")
        return

    print("☁️ Connecting to Azure Blob Storage to scan 'resourceblobs/' folder...")
    try:
        service_client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
        container_client = service_client.get_container_client(CONTAINER_NAME)
        
        blobs = container_client.list_blobs(name_starts_with="resourceblobs/")

        count = 0
        for blob in blobs:
            if blob.size > 0:
                blob_client = container_client.get_blob_client(blob.name)
                upload_blob_to_strapi(blob_client, blob.name)
                count += 1
                
        print(f"✨ Scanned {count} blobs in 'resourceblobs/'. Successfully mapped {len(MEDIA_CACHE)} images into Strapi.\n")
    except Exception as e:
        IMPORT_LOGS["warnings"].append(f"Azure sync error: {e}")
        print(f"❌ Azure connection error: {e}")


def decode_text(text: str, encoding: str) -> str:
    if not text or not isinstance(text, str):
        return str(text or "")
    if encoding == "plain" or (len(text) < 10 and not text.startswith("M")):
        return text
    try:
        if encoding == "lz-string:B64":
            decompressed = lz.decompressFromBase64(text)
            return decompressed if decompressed is not None else text
        elif encoding == "lz-string:UTF16":
            decompressed = lz.decompressFromUTF16(text)
            return decompressed if decompressed is not None else text
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
            decoded = decode_text(item.get("text", ""), item.get("encoding", ""))
            body_text += decoded + "\n\n"
        elif itype == "popup":
            body_text += f"\n[Popup: {item.get('title', item.get('name'))}]\n\n"
        elif itype == "container":
            for c_item in item.get("content", []):
                if isinstance(c_item, dict) and c_item.get("type") == "block-quote":
                    quotes.append({
                        "text": c_item.get("text", ""),
                        "citation": c_item.get("citation", "")
                    })
                elif isinstance(c_item, dict) and c_item.get("type") in ["reminders", "diary-calendar", "diarygraph"]:
                    body_text += f"\n[{c_item.get('type').upper()} WIDGET]\n\n"
                else:
                    IMPORT_LOGS["unhandled_blocks"].append({
                        "path": context_path,
                        "parent": "container_inside_block",
                        "block": c_item
                    })
        else:
            IMPORT_LOGS["unhandled_blocks"].append({
                "path": context_path,
                "parent": "nested_content_list",
                "block": item
            })

    return body_text.strip(), quotes


def transform_block(item: dict, page_route: str):
    if not isinstance(item, dict):
        return {
            "__component": "blocks.markdown",
            "text": str(item),
            "encoding": "plain"
        }

    item_type = item.get("type")

    if item_type == "markdown":
        raw_text = item.get("text", "")
        encoding = item.get("encoding", "")
        plain_text = decode_text(raw_text, encoding)
        return {
            "__component": "blocks.markdown",
            "text": plain_text,
            "encoding": "plain"
        }

    elif item_type in ["menu", "described-menu", "homepage-menu"]:
        menu_items = []
        raw_items = item.get("content", [])
        if "mainitems" in item:
            raw_items = item.get("mainitems", []) + item.get("sideitems", [])
            if "profiler" in item and isinstance(item["profiler"], dict):
                raw_items.append(item["profiler"])

        for mi in raw_items:
            if not isinstance(mi, dict):
                continue
            desc = mi.get("description", "")
            if isinstance(desc, dict):
                desc = decode_text(desc.get("text", ""), desc.get("encoding", ""))
            
            menu_items.append({
                "title": mi.get("title", ""),
                "link": mi.get("link", ""),
                "icon": mi.get("icon", "none"),
                "description": desc or ""
            })

        return {
            "__component": "blocks.menu",
            "menu_type": item_type,
            "items": menu_items
        }

    elif item_type == "accordion":
        acc_items = []
        for acc in item.get("content", []):
            if not isinstance(acc, dict):
                continue
            body_text, quotes = extract_quotes_and_body(acc.get("content", []), f"{page_route} -> Accordion[{acc.get('header')}]")
            acc_items.append({
                "header": acc.get("header", ""),
                "icon": acc.get("icon", "none"),
                "body": body_text,
                "quotes": quotes
            })
        return {
            "__component": "blocks.accordion",
            "items": acc_items
        }

    elif item_type == "popup":
        body_text, quotes = extract_quotes_and_body(item.get("content", []), f"{page_route} -> Popup[{item.get('name')}]")
        return {
            "__component": "blocks.popup",
            "name_key": item.get("name", ""),
            "title": item.get("title", ""),
            "size": item.get("size", "lg") or "lg",
            "body": body_text,
            "quotes": quotes
        }

    elif item_type == "standout":
        content_array = item.get("content", [{}])
        inner = content_array[0] if content_array and isinstance(content_array[0], dict) else {}
        raw_text = inner.get("text", "")
        encoding = inner.get("encoding", "")
        return {
            "__component": "blocks.standout",
            "class": item.get("class", "so-important"),
            "text": decode_text(raw_text, encoding)
        }

    elif item_type == "carousel":
        partner_items = []
        for slide in item.get("slides", []):
            if not isinstance(slide, dict):
                continue
            content = slide.get("content", {})
            if isinstance(content, dict) and content.get("type") == "tiledresources":
                for res_name in content.get("resources", []):
                    res_str = str(res_name).strip()
                    matched_media_id = None
                    for cached_filename, media_id in MEDIA_CACHE.items():
                        if res_str.lower() in cached_filename.lower():
                            matched_media_id = media_id
                            break

                    partner_items.append({
                        "name": res_str,
                        "url": "",
                        "logo": matched_media_id
                    })

        return {
            "__component": "blocks.partner-carousel",
            "name": item.get("name", "Logos"),
            "controls": item.get("controls", False),
            "indicators": item.get("indicators", True),
            "autostart": item.get("autostart", True),
            "partners": partner_items
        }

    elif item_type in [
        "goalsetter", "goalchecker", "diary-calendar", "diarygraph", 
        "reminders", "my-plans", "user-details-page", "my-personal-support", 
        "thoughts-page", "favourites-page", "index-list", "thoughts", "contacts-page",
        "fillin", "plan"
    ]:
        return {
            "__component": "blocks.interactive-tool",
            "tool_type": item_type,
            "config": {k: v for k, v in item.items() if k != "type"}
        }

    IMPORT_LOGS["unhandled_blocks"].append({
        "path": page_route,
        "parent": "root_dynamic_zone",
        "block": item
    })
    return None


def merge_json_files(content_path: str, structure_path: str, resources_path: str) -> dict:
    merged_data = {}
    for file_path in [content_path, structure_path, resources_path]:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                    for route, blocks in file_data.items():
                        if route not in merged_data:
                            merged_data[route] = []
                        if isinstance(blocks, list):
                            for b in blocks:
                                if b not in merged_data[route]:
                                    merged_data[route].append(b)
                print(f"📖 Loaded '{file_path}' ({len(file_data)} routes)")
            except Exception as e:
                IMPORT_LOGS["warnings"].append(f"Failed to read file '{file_path}': {e}")
        else:
            IMPORT_LOGS["warnings"].append(f"File not found: '{file_path}' - Skipping.")
    return merged_data


def import_all_to_strapi():
    sync_azure_media_library()

    merged_routes = merge_json_files("content.json", "structure.json", "resources.json")
    print(f"🚀 Starting page import/update of {len(merged_routes)} unique routes into Strapi...\n")

    rest_headers = {
        "Authorization": f"Bearer {STRAPI_API_TOKEN}",
        "Content-Type": "application/json",
    }

    for raw_route, blocks in merged_routes.items():
        # Clean the route to form a unique, full-path slug
        # e.g., "#home/dealing-se/sleep/help" becomes "home-dealing-se-sleep-help"
        slug = raw_route.lstrip("#").strip().replace("/", "-").lower()
        title = slug.split("-")[-1].replace("-", " ").title() or "Home"

        dynamic_zone_payload = []

        for block in blocks:
            if not isinstance(block, dict):
                continue

            if block.get("type") == "container":
                for inner_block in block.get("content", []):
                    if isinstance(inner_block, dict) and inner_block.get("type") == "block-quote":
                        dynamic_zone_payload.append({
                            "__component": "blocks.quote-block",
                            "quote_details": {
                                "text": inner_block.get("text", ""),
                                "citation": inner_block.get("citation", "")
                            }
                        })
                    else:
                        transformed = transform_block(inner_block, slug)
                        if transformed:
                            dynamic_zone_payload.append(transformed)
            else:
                transformed = transform_block(block, slug)
                if transformed:
                    dynamic_zone_payload.append(transformed)

        payload = {
            "data": {
                "title": title,
                "slug": slug,
                "content": dynamic_zone_payload
            }
        }

        try:
            # Check if page already exists by slug to perform an Upsert (Update vs Create)
            check_res = requests.get(f"{STRAPI_URL}/api/pages?filters[slug][$eq]={slug}", headers=rest_headers)
            existing_id = None
            if check_res.status_code == 200:
                data = check_res.json().get("data", [])
                if data:
                    existing_id = data[0]["id"]

            if existing_id:
                res = requests.put(f"{STRAPI_URL}/api/pages/{existing_id}", headers=rest_headers, json=payload)
                action = "Updated"
            else:
                res = requests.post(f"{STRAPI_URL}/api/pages", headers=rest_headers, json=payload)
                action = "Imported"

            if res.status_code in [200, 201]:
                print(f"✅ {action} Page: {slug}")
                IMPORT_LOGS["successful_pages"].append(slug)
            else:
                print(f"❌ API Error ({slug}): {res.status_code} - {res.text}")
                IMPORT_LOGS["failed_pages"].append({
                    "slug": slug,
                    "status_code": res.status_code,
                    "error": res.text
                })
        except Exception as e:
            IMPORT_LOGS["failed_pages"].append({
                "slug": slug,
                "status_code": "EXCEPTION",
                "error": str(e)
            })

    print_completion_report()


def print_completion_report():
    print("\n" + "=" * 80)
    print("AZURE MEDIA & MIGRATION REPORT")
    print("=" * 80)
    print(f"  • Successfully Uploaded Media Files : {len(IMPORT_LOGS['uploaded_media'])}")
    print(f"  • Failed Media Uploads             : {len(IMPORT_LOGS['failed_media'])}")
    print(f"  • Successful Pages Processed       : {len(IMPORT_LOGS['successful_pages'])}")
    print(f"  • Failed Pages (API Errors)         : {len(IMPORT_LOGS['failed_pages'])}")
    print(f"  • Unhandled/Unmapped Blocks        : {len(IMPORT_LOGS['unhandled_blocks'])}")
    print("=" * 80)


if __name__ == "__main__":
    import_all_to_strapi()