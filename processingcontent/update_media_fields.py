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
                # Strip file extensions (e.g., 'my-icon.png' -> 'my-icon') for safer matching
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

def process_item_block(item, media_map):
    """Processes menu items, items, or generic dictionary structures containing an icon field."""
    if not isinstance(item, dict):
        return item
        
    # Check if this object contains an 'icon' field
    if "icon" in item:
        icon_val = item.get("icon")
        # Map it into the new 'media' field while preserving 'icon' (text)
        item["media"] = resolve_media_id(icon_val, media_map)

    # Recursively look inside nested dictionary keys or arrays (like accordions or sub-components)
    for key, val in item.items():
        if isinstance(val, list):
            item[key] = [process_item_block(sub, media_map) for sub in val]
        elif isinstance(val, dict):
            item[key] = process_item_block(val, media_map)
            
    return item

def process_dynamic_zone_blocks(blocks, media_map):
    """Iterates through dynamic zone components on a page."""
    processed_blocks = []
    for block in blocks:
        if not isinstance(block, dict):
            processed_blocks.append(block)
            continue
            
        # Handle structural blocks like containers or custom components
        cleaned_block = process_item_block(block, media_map)
        processed_blocks.append(cleaned_block)
        
    return processed_blocks

def fetch_all_strapi_pages():
    """Paging through all pages collection entries."""
    all_pages = []
    page_num = 1
    page_size = 100

    print("📄 Fetching all pages from Strapi...")
    while True:
        # Populate content and components deeply so we can read the raw text icon fields
        query_params = f"pagination[page]={page_num}&pagination[pageSize]={page_size}&populate[content]=true"
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

def run_media_migration():
    media_map = get_media_library_map()
    pages = fetch_all_strapi_pages()
    
    print(f"\n🔄 Scanning {len(pages)} pages to inject media relations based on text 'icon' fields...")
    
    updated_count = 0
    for page in pages:
        doc_id = page.get("documentId")
        slug = page.get("slug")
        content = page.get("content", [])
        
        if not content:
            continue

        # Process dynamic zones and all nested component items (menu_item, accordion_item, items, etc.)
        updated_content = process_dynamic_zone_blocks(content, media_map)

        # Send update back to Strapi
        update_res = requests.put(
            f"{STRAPI_URL}/api/pages/{doc_id}", 
            headers=HEADERS, 
            json={
                "data": {
                    "content": updated_content
                }
            }
        )

        if update_res.status_code in [200, 201]:
            print(f"✅ Updated media fields for page: slug='{slug}'")
            updated_count += 1
        else:
            print(f"❌ Failed to update page slug='{slug}': {update_res.text}")

    print(f"\n✨ Migration Complete! Successfully updated media bindings across {updated_count} pages.")

if __name__ == "__main__":
    run_media_migration()