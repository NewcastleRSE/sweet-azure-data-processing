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

def get_media_library_map():
    """Fetches all files from the Strapi Media Library and builds a filename-to-ID lookup map."""
    print("📁 Fetching media library files from Strapi...")
    media_map = {}
    page = 1
    
    while True:
        res = requests.get(f"{STRAPI_URL}/api/upload/files?pagination[page]={page}&pagination[pageSize]=250", headers=HEADERS)
        if res.status_code != 200:
            print(f"⚠️ Failed to fetch upload files: {res.text}")
            break
            
        files = res.json()
        if not files:
            break
            
        for file in files:
            name = file.get("name")
            file_id = file.get("id")
            if name:
                media_map[name] = file_id
                media_map[name.lower()] = file_id
                # Strip file extensions (e.g., 'icon.png' -> 'icon') for safer matching
                base_name = os.path.splitext(name)[0]
                media_map[base_name] = file_id
                media_map[base_name.lower()] = file_id

        if len(files) < 250:
            break
        page += 1

    print(f"✅ Loaded {len(media_map)} reference entries from the Media Library.")
    return media_map

def resolve_media_id(icon_value, media_map):
    """Matches a text icon string to a media library file ID."""
    if not icon_value or icon_value == "none":
        return None
        
    if isinstance(icon_value, (int, float)):
        return int(icon_value)
        
    if isinstance(icon_value, str):
        clean_name = icon_value.split("/")[-1].strip()
        matched_id = media_map.get(clean_name) or media_map.get(clean_name.lower())
        if not matched_id:
            base_name = os.path.splitext(clean_name)[0]
            matched_id = media_map.get(base_name) or media_map.get(base_name.lower())
        return matched_id
        
    return None

def fetch_all_strapi_pages():
    """Paging through all pages collection entries with deep component population."""
    all_pages = []
    page_num = 1
    page_size = 100

    print("📄 Fetching all pages from Strapi...")
    while True:
        # Deep populate dynamic zone blocks and their internal sub-components (like items in accordions and menus)
        query_params = f"pagination[page]={page_num}&pagination[pageSize]={page_size}&populate[content][populate]=*"
        res = requests.get(f"{STRAPI_URL}/api/pages?{query_params}", headers=HEADERS)
        
        if res.status_code != 200:
            print(f"❌ Failed to fetch page batch {page_num}: {res.text}")
            break

        data_json = res.json()
        pages = data_json.get("data", [])
        if not pages:
            break

        all_pages.extend(pages)
        meta = data_json.get("meta", {}).get("pagination", {})
        if page_num >= meta.get("pageCount", 1):
            break
        page_num += 1

    return all_pages

def process_block_items(items, media_map):
    """Helper to loop through list items (e.g., accordion items or menu items) and bind media."""
    modified = False
    if not isinstance(items, list):
        return modified

    for item in items:
        if isinstance(item, dict) and "icon" in item:
            icon_val = item.get("icon")
            resolved_id = resolve_media_id(icon_val, media_map)
            
            if resolved_id:
                item["media"] = resolved_id
                modified = True
                
    return modified

def run_media_migration():
    media_map = get_media_library_map()
    pages = fetch_all_strapi_pages()
    
    print(f"\n🔄 Scanning {len(pages)} pages for Accordion and Menu blocks...")
    
    updated_count = 0
    for page in pages:
        doc_id = page.get("documentId")
        slug = page.get("slug")
        content = page.get("content", [])
        
        if not content:
            continue

        page_modified = False

        # Iterate through dynamic zone blocks
        for block in content:
            if not isinstance(block, dict):
                continue
                
            component_type = block.get("__component", "").lower()
            
            # Target Accordion blocks and Menu blocks (or any block featuring an 'items' array)
            if "accordion" in component_type or "menu" in component_type:
                items = block.get("items", [])
                if process_block_items(items, media_map):
                    page_modified = True

        # If any accordion or menu items were updated, push the changes back to Strapi
        if page_modified:
            update_res = requests.put(
                f"{STRAPI_URL}/api/pages/{doc_id}", 
                headers=HEADERS, 
                json={
                    "data": {
                        "content": content
                    }
                }
            )

            if update_res.status_code in [200, 201]:
                print(f"✅ Updated media bindings for page: slug='{slug}'")
                updated_count += 1
            else:
                print(f"❌ Failed to update page slug='{slug}': {update_res.text}")

    print(f"\n✨ Migration Complete! Successfully updated accordion and menu media links across {updated_count} pages.")

if __name__ == "__main__":
    run_media_migration()