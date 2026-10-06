import os
import re
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

INPUT_FILE = "processingcontent/old_site_heroes.json"

# Base64/data-uri leftovers look like this rather than real filenames
BASE64_FRAGMENT_RE = re.compile(r"^[A-Za-z0-9+/]+=*$")

def looks_like_base64_fragment(name):
    if not name:
        return False
    if "=" in name:
        return True
    if len(name) >= 16 and "-" not in name and "_" not in name and BASE64_FRAGMENT_RE.match(name):
        return True
    return False

REQUEST_TIMEOUT = 15
PUT_TIMEOUT = 8

def fetch_page_by_slug(slug):
    res = requests.get(
        f"{STRAPI_URL}/api/pages",
        headers=HEADERS,
        params={"filters[slug][$eq]": slug, "populate": "Hero"},
        timeout=REQUEST_TIMEOUT
    )
    res.raise_for_status()
    data = res.json().get("data", [])
    return data[0] if data else None

def find_media_match(filename):
    """Searches the Media Library for an asset whose name contains the given filename."""
    res = requests.get(
        f"{STRAPI_URL}/api/upload/files",
        headers=HEADERS,
        params={"filters[name][$containsi]": filename},
        timeout=REQUEST_TIMEOUT
    )
    res.raise_for_status()
    matches = res.json()
    return matches[0] if matches else None

def set_hero(document_id, media_id):
    """Sends the update. This Strapi instance sometimes hangs on the PUT response
    even though the write succeeds, so a read timeout is treated as 'unknown' and
    verified afterwards with a fresh GET rather than retried."""
    try:
        res = requests.put(
            f"{STRAPI_URL}/api/pages/{document_id}",
            headers=HEADERS,
            params={"fields[0]": "slug"},
            json={"data": {"Hero": {"image": media_id}}},
            timeout=PUT_TIMEOUT
        )
        if res.status_code not in (200, 201):
            print(f"   ❌ Failed to set Hero: [{res.status_code}] {res.text}")
            return False
        return True
    except requests.exceptions.ReadTimeout:
        return None  # unknown outcome, caller should verify

def main():
    with open(INPUT_FILE, encoding="utf-8") as f:
        entries = json.load(f)

    no_old_page = []
    no_hero_on_old_site = []
    inline_image_only = []
    no_media_match = []
    updated = []

    for i, entry in enumerate(entries, start=1):
        slug = entry["slug"]
        title = entry.get("title") or ""
        filename = entry.get("filename")
        print(f"[{i}/{len(entries)}] {slug}", flush=True)

        if re.search(r"404|Not Found", title, re.IGNORECASE):
            no_old_page.append(slug)
            continue

        if not filename:
            no_hero_on_old_site.append(slug)
            continue

        if looks_like_base64_fragment(filename):
            inline_image_only.append(slug)
            continue

        try:
            page = fetch_page_by_slug(slug)
        except requests.RequestException as e:
            print(f"   ⚠️ Error fetching page '{slug}': {e}", flush=True)
            continue
        if not page:
            print(f"   ⚠️ '{slug}' not found in Strapi pages, skipping.", flush=True)
            continue

        if page.get("Hero"):
            continue  # already has a hero, don't overwrite

        try:
            media = find_media_match(filename)
        except requests.RequestException as e:
            print(f"   ⚠️ Error searching media for '{filename}': {e}", flush=True)
            continue
        if not media:
            no_media_match.append({"slug": slug, "filename": filename})
            continue

        document_id = page.get("documentId") or page.get("id")
        try:
            success = set_hero(document_id, media["id"])
        except requests.RequestException as e:
            print(f"   ⚠️ Error setting Hero for '{slug}': {e}", flush=True)
            success = None

        if success is None:
            # PUT response hung/timed out; verify the write actually landed
            try:
                verify_page = fetch_page_by_slug(slug)
                success = bool(verify_page and verify_page.get("Hero"))
            except requests.RequestException as e:
                print(f"   ⚠️ Error verifying Hero for '{slug}': {e}", flush=True)
                success = False

        if success:
            print(f"   ✅ Set Hero for '{slug}' -> media '{media['name']}' (matched '{filename}')", flush=True)
            updated.append({"slug": slug, "filename": filename, "media": media["name"]})
        else:
            no_media_match.append({"slug": slug, "filename": filename, "error": "request kept timing out"})

    print("\n========================================")
    print(f"✨ Done. Updated: {len(updated)}")
    print("========================================")

    print(f"\n🔍 No equivalent page on the old site ({len(no_old_page)}):")
    for slug in no_old_page:
        print(f"   • {slug}")

    print(f"\n🔍 Old site page has no hero image either ({len(no_hero_on_old_site)}):")
    for slug in no_hero_on_old_site:
        print(f"   • {slug}")

    print(f"\n🔍 Old site hero is an inline/base64 image, no filename to match ({len(inline_image_only)}):")
    for slug in inline_image_only:
        print(f"   • {slug}")

    print(f"\n❌ Could not find a matching Strapi media asset ({len(no_media_match)}):")
    for item in no_media_match:
        print(f"   • {item['slug']}  (looking for '{item['filename']}')")

    with open("processingcontent/hero_match_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "updated": updated,
            "no_old_page": no_old_page,
            "no_hero_on_old_site": no_hero_on_old_site,
            "inline_image_only": inline_image_only,
            "no_media_match": no_media_match,
        }, f, indent=2)

if __name__ == "__main__":
    main()
