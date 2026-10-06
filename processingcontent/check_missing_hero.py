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

def fetch_all_pages():
    pages = []
    page_num = 1
    page_size = 100
    while True:
        res = requests.get(
            f"{STRAPI_URL}/api/pages",
            headers=HEADERS,
            params={
                "populate": "Hero",
                "fields[0]": "title",
                "fields[1]": "slug",
                "pagination[page]": page_num,
                "pagination[pageSize]": page_size,
            }
        )
        res.raise_for_status()
        body = res.json()
        pages.extend(body.get("data", []))
        meta = body.get("meta", {}).get("pagination", {})
        if page_num >= meta.get("pageCount", 1):
            break
        page_num += 1
    return pages

def main():
    pages = fetch_all_pages()
    missing = [p for p in pages if not p.get("Hero")]

    print(f"🔍 Checked {len(pages)} pages, {len(missing)} are missing a Hero image:\n")
    for p in sorted(missing, key=lambda x: x.get("slug") or ""):
        print(f"   • {p.get('title') or '(untitled)'}  —  slug: {p.get('slug')}")

if __name__ == "__main__":
    main()
