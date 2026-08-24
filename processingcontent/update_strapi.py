import json
import os
import requests
from lzstring import LZString
from dotenv import load_dotenv

load_dotenv()

STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

lz = LZString()
ENDPOINT = "/api/pages"

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
                elif isinstance(desc, str) and len(desc) > 5 and desc.startswith("M"):
                    desc = decode_text(desc, mi.get("encoding", "lz-string:B64"))
                
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

def merge_json_files(content_path, structure_path):
    merged_data = {}
    if os.path.exists(content_path):
        with open(content_path, "r", encoding="utf-8") as f:
            try:
                content_data = json.load(f)
                for route, blocks in content_data.items():
                    if route.startswith("#"):
                        clean_route = "#" + route.lstrip("#").strip().lower()
                        if clean_route not in merged_data:
                            merged_data[clean_route] = []
                        block_list = blocks if isinstance(blocks, list) else [blocks]
                        for b in block_list:
                            if b not in merged_data[clean_route]:
                                merged_data[clean_route].append(b)
            except Exception as e:
                print(f"⚠️ Error reading {content_path}: {e}")

    if os.path.exists(structure_path):
        with open(structure_path, "r", encoding="utf-8") as f:
            try:
                struct_data = json.load(f)
                def extract_routes(node):
                    if isinstance(node, dict):
                        route = node.get("route", node.get("link", ""))
                        if route and route.startswith("#"):
                            clean_route = "#" + route.lstrip("#").strip().lower()
                            if clean_route not in merged_data:
                                merged_data[clean_route] = []
                        for k, v in node.items():
                            if isinstance(v, (dict, list)):
                                extract_routes(v)
                    elif isinstance(node, list):
                        for item in node:
                            extract_routes(item)
                extract_routes(struct_data)
            except Exception as e:
                print(f"⚠️ Error reading {structure_path}: {e}")

    return merged_data

def fetch_all_strapi_pages():
    all_pages = []
    page_num = 1
    page_size = 100

    print("📄 Fetching all pages from Strapi (handling pagination)...")
    while True:
        query_params = f"pagination[page]={page_num}&pagination[pageSize]={page_size}"
        res = requests.get(f"{STRAPI_URL}{ENDPOINT}?{query_params}", headers=HEADERS)
        
        if res.status_code != 200:
            print(f"❌ Failed to fetch page {page_num} from Strapi: {res.text}")
            break

        data_json = res.json()
        pages = data_json.get("data", [])
        if not pages:
            break

        all_pages.extend(pages)
        print(f"   - Fetched batch {page_num} ({len(pages)} entries)...")

        meta = data_json.get("meta", {}).get("pagination", {})
        total_pages = meta.get("pageCount", 1)

        if page_num >= total_pages:
            break
        page_num += 1

    return all_pages

def run_content_update():
    print("🔄 Starting Strapi Content, Title, and Decoding Sync...")
    
    merged_routes = merge_json_files("content.json", "structure.json")
    structure_titles = load_structure_titles("structure.json")

    route_payload_cache = {}
    for raw_route, blocks in merged_routes.items():
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

        route_payload_cache[slug] = {
            "title": title,
            "content": dynamic_zone_payload
        }

    strapi_pages = fetch_all_strapi_pages()
    print(f"📄 Found {len(strapi_pages)} total pages in Strapi. Updating titles, descriptions, and decoded text...")

    for page in strapi_pages:
        doc_id = page.get("documentId")
        slug = page.get("slug")
        
        if slug in route_payload_cache:
            payload_data = route_payload_cache[slug]
            
            update_res = requests.put(f"{STRAPI_URL}{ENDPOINT}/{doc_id}", headers=HEADERS, json={
                "data": payload_data
            })
            
            if update_res.status_code in [200, 201]:
                print(f"✅ Updated slug='{slug}' -> Title: '{payload_data['title']}' ({len(payload_data['content'])} decoded blocks)")
            else:
                print(f"❌ Failed updating slug='{slug}': {update_res.text}")
        else:
            print(f"⚠️ No local source data found for Strapi slug='{slug}'")

    print("\n✨ Update Complete! All titles, menu descriptions, and text encodings have been refreshed across all entries.")

if __name__ == "__main__":
    run_content_update()