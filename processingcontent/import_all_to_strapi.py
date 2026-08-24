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
ENDPOINT = "/api/pages"

IMPORT_LOGS = {
    "successful_pages": [],
    "failed_pages": [],
    "uploaded_media": [],
    "failed_media": [],
}

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
        print("ℹ️ Skipping Azure Media sync (No connection string provided).")
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

def extract_deep_text(data) -> str:
    """Recursively pulls all text elements from nested dictionaries or lists."""
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ["text", "body", "content", "title", "description", "header"]:
            if key in data:
                res = extract_deep_text(data[key])
                if res:
                    return res
        return " ".join([extract_deep_text(v) for v in data.values() if v])
    if isinstance(data, list):
        return "\n".join([extract_deep_text(item) for item in data if item])
    return ""

def load_structure_titles(structure_path: str) -> dict:
    """Recursively walks structure.json to build a map of route -> title"""
    title_map = {}
    if not os.path.exists(structure_path):
        return title_map

    try:
        with open(structure_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
            def recurse_node(node, current_path=""):
                if isinstance(node, dict):
                    route = node.get("route", node.get("link", ""))
                    title = node.get("title", "")
                    
                    if route and title:
                        clean_route = "#" + route.lstrip("#").strip().lower()
                        title_map[clean_route] = title
                        
                    for k, v in node.items():
                        if k.lower() in ["title", "name"] and isinstance(v, str) and current_path:
                            title_map[current_path] = v
                        elif isinstance(v, (dict, list)):
                            next_path = current_path if not k.startswith("#") else k
                            recurse_node(v, next_path)
                            
                elif isinstance(node, list):
                    for item in node:
                        recurse_node(item, current_path)
            
            recurse_node(data)
    except Exception as e:
        print(f"⚠️ Error parsing structure.json titles: {e}")
        
    return title_map

def route_to_slug(raw_route: str) -> str:
    clean = raw_route.lstrip("#").strip()
    if not clean or clean.lower() == "home":
        return "home"
    return clean.replace("/", "_").lower()

def transform_block(item: dict, page_route: str):
    if not isinstance(item, dict):
        return {"__component": "blocks.markdown", "text": str(item)}

    item_type = item.get("type")
    
    if item_type == "markdown":
        return {
            "__component": "blocks.markdown",
            "text": decode_text(item.get("text", ""), item.get("encoding", ""))
        }
    
    elif item_type in ["menu", "described-menu", "homepage-menu"]:
        menu_items = []
        
        def add_items(raw_list, role_name):
            for mi in raw_list:
                if not isinstance(mi, dict):
                    continue
                desc = mi.get("description", "")
                if isinstance(desc, dict):
                    desc = decode_text(desc.get("text", ""), desc.get("encoding", ""))
                
                menu_items.append({
                    "title": mi.get("title", ""),
                    "link": mi.get("link", ""),
                    "icon": mi.get("icon", "none"),
                    "description": desc or "",
                    "role": role_name
                })

        if "mainitems" in item:
            add_items(item.get("mainitems", []), "main")
            add_items(item.get("sideitems", []), "side")
            if "profiler" in item and isinstance(item["profiler"], dict):
                add_items([item["profiler"]], "profiler")
        else:
            add_items(item.get("content", []), "main")

        return {
            "__component": "blocks.menu",
            "menu_type": item_type,
            "items": menu_items
        }

    elif item_type == "accordion":
        acc_items = []
        for acc in item.get("content", []):
            if isinstance(acc, dict):
                body_text = extract_deep_text(acc.get("content", []))
                acc_items.append({
                    "header": acc.get("header", ""),
                    "icon": acc.get("icon", "none"),
                    "body": body_text.strip()
                })
        return {"__component": "blocks.accordion", "items": acc_items}

    elif item_type in ["carousel", "slideshow", "image-gallery"]:
        carousel_slides = []
        slides_data = item.get("content", item.get("slides", item.get("items", [])))
        
        if isinstance(slides_data, dict):
            slides_data = slides_data.get("content", slides_data.get("slides", [slides_data]))

        for slide in slides_data:
            if isinstance(slide, dict):
                slide_content = slide.get("content", {})
                if isinstance(slide_content, dict) and slide_content.get("type") == "tiledresources":
                    resources = slide_content.get("resources", [])
                    slide_text = ", ".join(resources)
                else:
                    slide_text = decode_text(
                        slide.get("text", slide.get("description", slide.get("body", extract_deep_text(slide)))), 
                        slide.get("encoding", "")
                    )

                carousel_slides.append({
                    "title": slide.get("title", slide.get("header", "")),
                    "text": slide_text,
                    "image_url": slide.get("image", slide.get("url", slide.get("src", "")))
                })
        
        return {
            "__component": "blocks.interactive-tool",
            "tool_type": "carousel",
            "config": {
                "slides": carousel_slides, 
                "name": item.get("name", ""),
                "controls": item.get("controls", True),
                "indicators": item.get("indicators", True),
                "darkmode": item.get("darkmode", True),
                "autostart": item.get("autostart", True)
            }
        }

    elif item_type == "block-quote":
        return {
            "__component": "blocks.markdown",
            "text": f"> {decode_text(item.get('text', ''), item.get('encoding', ''))}"
        }

    elif item_type == "popup":
        popup_content = extract_deep_text(item.get("content", []))
        return {
            "__component": "blocks.interactive-tool",
            "tool_type": "popup",
            "config": {
                "title": item.get("title", "Popup Info"),
                "body": popup_content.strip(),
                **{k: v for k, v in item.items() if k not in ["type", "content"]}
            }
        }

    elif item_type in ["standout", "so-important"]:
        inner = item.get("content", [{}])[0] if item.get("content") else {}
        if isinstance(inner, dict):
            text_val = inner.get("text", extract_deep_text(inner))
        else:
            text_val = str(inner)
        return {
            "__component": "blocks.standout",
            "class": item.get("class", "so-important"),
            "text": decode_text(text_val, inner.get("encoding", "") if isinstance(inner, dict) else "")
        }

    elif item_type in ["goalsetter", "goalchecker", "diary-calendar", "diarygraph", "reminders", "my-plans", "user-details-page", "my-personal-support", "thoughts-page", "favourites-page", "index-list", "thoughts", "contacts-page", "fillin", "plan", "interactive-tool", "tiledresources"]:
        return {
            "__component": "blocks.interactive-tool",
            "tool_type": item_type,
            "config": {k: v for k, v in item.items() if k != "type"}
        }

    return None

def merge_json_files(content_path, structure_path, resources_path):
    merged_data = {}
    for file_path in [content_path, structure_path, resources_path]:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    file_data = json.load(f)
                    for route, blocks in file_data.items():
                        clean_route = "#" + route.lstrip("#").strip().lower()
                        
                        if clean_route not in merged_data:
                            merged_data[clean_route] = []
                            
                        block_list = blocks
                        if isinstance(blocks, dict):
                            for wrapper in ["content", "blocks", "layout", "pages", "body"]:
                                if wrapper in blocks and isinstance(blocks[wrapper], list):
                                    block_list = blocks[wrapper]
                                    break
                            else:
                                block_list = [blocks]

                        if isinstance(block_list, list):
                            for b in block_list:
                                if b not in merged_data[clean_route]:
                                    merged_data[clean_route].append(b)
                except Exception as e:
                    print(f"⚠️ Error reading {file_path}: {e}")
    return merged_data

def run_full_migration():
    sync_azure_media_library()

    merged_routes = merge_json_files("content.json", "structure.json", "resources.json")
    structure_titles = load_structure_titles("structure.json")
    print(f"🚀 Merged and scanning {len(merged_routes)} unique routes across source files...")

    slug_to_doc_id = {}
    sorted_routes = sorted(merged_routes.keys(), key=lambda r: r.count("/"))

    # ---------------------------------------------------------
    # PASS 1: Create or Refresh All Pages From Scratch
    # ---------------------------------------------------------
    print("\n--- PASS 1: Creating Pages & Dynamic Zones ---")
    for raw_route in sorted_routes:
        blocks = merged_routes[raw_route]
        slug = route_to_slug(raw_route)
        
        clean_lookup_route = "#" + raw_route.lstrip("#").strip().lower()
        title = structure_titles.get(clean_lookup_route)
        if not title:
            title = structure_titles.get(raw_route.lstrip("#").strip().lower())
        if not title:
            title = slug.split("_")[-1].replace("-", " ").title() or "Home"

        dynamic_zone_payload = []
        for block in blocks:
            if isinstance(block, dict):
                if block.get("type") == "container":
                    inner_content = block.get("content", [])
                    if isinstance(inner_content, list):
                        for inner in inner_content:
                            t = transform_block(inner, slug)
                            if t: dynamic_zone_payload.append(t)
                    else:
                        t = transform_block(block, slug)
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

        check_res = requests.get(f"{STRAPI_URL}{ENDPOINT}?filters[slug][$eq]={slug}", headers=HEADERS)
        existing_doc_id = None
        
        if check_res.status_code == 200:
            existing_data = check_res.json().get("data", [])
            if existing_data:
                existing_doc_id = existing_data[0].get("documentId")

        if existing_doc_id:
            res = requests.put(f"{STRAPI_URL}{ENDPOINT}/{existing_doc_id}", headers=HEADERS, json=payload)
            doc_id = existing_doc_id
            action = "Refreshed/Updated"
        else:
            res = requests.post(f"{STRAPI_URL}{ENDPOINT}", headers=HEADERS, json=payload)
            doc_id = None
            if res.text:
                try:
                    res_json = res.json()
                    res_data = res_json.get("data", res_json)
                    if isinstance(res_data, dict):
                        doc_id = res_data.get("documentId")
                except Exception:
                    pass
            
            if not doc_id and res.status_code in [200, 201]:
                fb_res = requests.get(f"{STRAPI_URL}{ENDPOINT}?filters[slug][$eq]={slug}", headers=HEADERS)
                if fb_res.status_code == 200:
                    fb_data = fb_res.json().get("data", [])
                    if fb_data:
                        doc_id = fb_data[0].get("documentId")

            action = "Created"

        if res.status_code in [200, 201] and doc_id:
            slug_to_doc_id[slug] = doc_id
            print(f"✅ {action}: slug='{slug}' (Title: '{title}') with {len(dynamic_zone_payload)} blocks")
            IMPORT_LOGS["successful_pages"].append(slug)
        else:
            print(f"❌ Failed '{slug}': {res.status_code} - {res.text}")
            IMPORT_LOGS["failed_pages"].append({"slug": slug, "error": res.text})

    # ---------------------------------------------------------
    # PASS 2: Universal Tree Linking & Children Flush
    # ---------------------------------------------------------
    print("\n--- PASS 2: Linking Parent/Child Hierarchies ---")
    parent_to_children_docs = {}

    for raw_route in sorted_routes:
        clean_route = raw_route.lstrip("#").strip()
        if not clean_route or clean_route.lower() == "home":
            continue

        child_slug = route_to_slug(raw_route)
        
        segments = clean_route.split("/")
        if len(segments) <= 1:
            continue
            
        parent_segments = segments[:-1]
        parent_raw = "#" + "/".join(parent_segments)
        parent_slug = route_to_slug(parent_raw)

        child_doc_id = slug_to_doc_id.get(child_slug)
        parent_doc_id = slug_to_doc_id.get(parent_slug)

        if child_doc_id and parent_doc_id:
            child_res = requests.put(f"{STRAPI_URL}{ENDPOINT}/{child_doc_id}", headers=HEADERS, json={
                "data": { "parent": parent_doc_id }
            })
            if child_res.status_code in [200, 201]:
                print(f"🔗 Linked child '{child_slug}' -> parent '{parent_slug}'")
            else:
                print(f"❌ Failed linking child '{child_slug}': {child_res.text}")

            if parent_doc_id not in parent_to_children_docs:
                parent_to_children_docs[parent_doc_id] = []
            if child_doc_id not in parent_to_children_docs[parent_doc_id]:
                parent_to_children_docs[parent_doc_id].append(child_doc_id)
        else:
            print(f"⚠️ Warning: Missing mapping IDs -> child('{child_slug}'): {child_doc_id}, parent('{parent_slug}'): {parent_doc_id}")

    print("\n--- Flushing Complete Children Arrays to Parents ---")
    for parent_doc_id, child_ids in parent_to_children_docs.items():
        parent_res = requests.put(f"{STRAPI_URL}{ENDPOINT}/{parent_doc_id}", headers=HEADERS, json={
            "data": { 
                "children": {
                    "set": child_ids
                }
            }
        })
        if parent_res.status_code in [200, 201]:
            print(f"📂 Updated parent ID '{parent_doc_id}' with {len(child_ids)} child record(s).")
        else:
            print(f"❌ Failed updating parent collection '{parent_doc_id}': {parent_res.text}")

    print(f"\n✨ Full Migration Complete! Successfully processed {len(IMPORT_LOGS['successful_pages'])} pages.")

if __name__ == "__main__":
    run_full_migration()