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

ENDPOINT = "/api/pages"

def fetch_all_strapi_pages():
    all_pages = []
    page_num = 1
    page_size = 100  # Safe batch size for Strapi limits

    print("📄 Fetching all pages from Strapi (handling pagination)...")
    while True:
        query_params = (
            f"pagination[page]={page_num}&pagination[pageSize]={page_size}"
            "&populate[content]=true&populate[parent]=true&populate[children]=true"
        )
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

        # Check pagination meta to see if there are more pages
        meta = data_json.get("meta", {}).get("pagination", {})
        total_pages = meta.get("pageCount", 1)

        if page_num >= total_pages:
            break
        page_num += 1

    return all_pages

def delete_empty_orphaned_pages():
    strapi_pages = fetch_all_strapi_pages()
    print(f"\n🔎 Scanning total of {len(strapi_pages)} pages for empty, orphaned entries...")

    deleted_count = 0
    kept_count = 0

    for page in strapi_pages:
        doc_id = page.get("documentId")
        slug = page.get("slug")
        title = page.get("title")
        
        content = page.get("content", [])
        parent = page.get("parent")
        children = page.get("children", [])

        # Safety check: Never delete the 'home' page
        if slug == "home":
            kept_count += 1
            continue

        # Criteria check: Must have no content, no parent, and no children
        is_empty_content = not content or len(content) == 0
        has_no_parent = parent is None
        has_no_children = not children or len(children) == 0

        if is_empty_content and has_no_parent and has_no_children:
            del_res = requests.delete(f"{STRAPI_URL}{ENDPOINT}/{doc_id}", headers=HEADERS)
            if del_res.status_code in [200, 204]:
                print(f"🗑️ Deleted empty orphaned page: slug='{slug}' (Title: '{title}', ID: {doc_id})")
                deleted_count += 1
            else:
                print(f"❌ Failed to delete slug='{slug}': {del_res.text}")
        else:
            kept_count += 1

    print(f"\n✨ Cleanup Complete!")
    print(f"   - Kept valid/populated pages: {kept_count}")
    print(f"   - Deleted empty orphaned pages: {deleted_count}")

if __name__ == "__main__":
    delete_empty_orphaned_pages()