import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

STRAPI_URL = os.getenv("STRAPI_URL", "http://localhost:1337").rstrip("/")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {STRAPI_API_TOKEN}",
    "Content-Type": "application/json"
}

ENDPOINT = "/api/pages"

def route_to_slug(raw_route: str) -> str:
    """Converts #home/goals-and-plans to home_goals-and-plans (slashes to underscores)"""
    clean = raw_route.lstrip("#").strip()
    if not clean or clean.lower() == "home":
        return "home"
    return clean.replace("/", "_").lower()

def transform_block(item: dict):
    if not isinstance(item, dict):
        return {"__component": "blocks.markdown", "text": str(item)}

    b_type = item.get("type")
    if b_type == "markdown":
        return {"__component": "blocks.markdown", "text": item.get("text", "")}
    elif b_type in ["menu", "described-menu", "homepage-menu"]:
        menu_items = []
        raw_items = item.get("content", [])
        if "mainitems" in item:
            raw_items = item.get("mainitems", []) + item.get("sideitems", [])
        for mi in raw_items:
            if isinstance(mi, dict):
                desc = mi.get("description", "")
                if isinstance(desc, dict):
                    desc = desc.get("text", "")
                menu_items.append({
                    "title": mi.get("title", ""),
                    "link": mi.get("link", ""),
                    "icon": mi.get("icon", "none"),
                    "description": desc or ""
                })
        return {"__component": "blocks.menu", "menu_type": b_type, "items": menu_items}
    return None

def run_hierarchy_test():
    if not os.path.exists("test_content.json"):
        print("❌ Error: test_content.json not found.")
        return

    with open("content.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"🧪 Running underscore slug & tree test on {len(data)} routes...\n")
    slug_to_doc_id = {}
    
    # Sort routes by path depth (parents first)
    sorted_routes = sorted(data.keys(), key=lambda r: r.count("/"))

    # ---------------------------------------------------------
    # PASS 1: Create or Update all pages using underscore slugs
    # ---------------------------------------------------------
    print("--- PASS 1: Creating Pages ---")
    for raw_route in sorted_routes:
        slug = route_to_slug(raw_route)
        title = slug.split("_")[-1].replace("-", " ").title() or "Home"

        dynamic_zone_payload = []
        for block in data[raw_route]:
            if isinstance(block, dict) and block.get("type") == "container":
                for inner in block.get("content", []):
                    t = transform_block(inner)
                    if t: dynamic_zone_payload.append(t)
            else:
                t = transform_block(block)
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
            action = "Updated"
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
            print(f"✅ {action}: slug='{slug}' (docId: {doc_id})")
        else:
            print(f"❌ Failed '{slug}': {res.status_code} - {res.text}")

    # ---------------------------------------------------------
    # PASS 2: Universal Tree Linking (Safe Aggregated Flush)
    # ---------------------------------------------------------
    print("\n--- PASS 2: Linking Parent/Child Tree ---")
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
            # 1. Link child -> parent (sets single parent field on child)
            child_res = requests.put(f"{STRAPI_URL}{ENDPOINT}/{child_doc_id}", headers=HEADERS, json={
                "data": { "parent": parent_doc_id }
            })
            if child_res.status_code in [200, 201]:
                print(f"🔗 Linked child '{child_slug}' -> parent '{parent_slug}'")
            else:
                print(f"❌ Failed linking child '{child_slug}': {child_res.text}")

            # 2. Safely collect children into our python dictionary mapping
            if parent_doc_id not in parent_to_children_docs:
                parent_to_children_docs[parent_doc_id] = []
            if child_doc_id not in parent_to_children_docs[parent_doc_id]:
                parent_to_children_docs[parent_doc_id].append(child_doc_id)
        else:
            print(f"⚠️ Warning: Missing mapping IDs -> child('{child_slug}'): {child_doc_id}, parent('{parent_slug}'): {parent_doc_id}")

    # Flush all collected children arrays to their respective parents ONCE
    print("\n--- Flushing Complete Children Arrays to Parents ---")
    for parent_doc_id, child_ids in parent_to_children_docs.items():
        print(f"📂 Setting {len(child_ids)} child(ren) for parent ID '{parent_doc_id}'...")
        parent_res = requests.put(f"{STRAPI_URL}{ENDPOINT}/{parent_doc_id}", headers=HEADERS, json={
            "data": { 
                "children": {
                    "set": child_ids
                }
            }
        })
        if parent_res.status_code in [200, 201]:
            print(f"   ✅ Successfully updated parent collection with: {child_ids}")
        else:
            print(f"   ❌ Failed updating parent collection: {parent_res.status_code} - {parent_res.text}")

    print("\n✨ Test Complete!")

if __name__ == "__main__":
    run_hierarchy_test()