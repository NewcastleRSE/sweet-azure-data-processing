import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

STRAPI_URL = os.getenv("STRAPI_URL")
STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

# Fallback check if uppercase variants are used in .env instead
if not STRAPI_URL:
    STRAPI_URL = os.getenv("STRAPI_URL")
if not STRAPI_API_TOKEN:
    STRAPI_API_TOKEN = os.getenv("STRAPI_API_TOKEN")

if not STRAPI_URL or not STRAPI_API_TOKEN:
    raise ValueError("Missing strapi_url or strapi_api_token in your .env file.")

# Ensure no trailing slash on the URL
STRAPI_URL = STRAPI_URL.rstrip('/')

# Path to your JSON file
JSON_FILE_PATH = "emailMessages.json"

def import_emails():
    # Read the JSON file
    if not os.path.exists(JSON_FILE_PATH):
        print(f"Error: Could not find {JSON_FILE_PATH}")
        return

    with open(JSON_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Endpoint for your messages collection (adjust 'messages' if your API plural ID is different)
    endpoint = f"{STRAPI_URL}/api/messages"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {STRAPI_API_TOKEN}"
    }

    # Loop through each key in the JSON object
    for key, content in data.items():
        print(f"Processing message type: {key}")

        # Extract fields matching your JSON structure
        subject = content.get("subject")
        html_content = content.get("html")
        plain_content = content.get("plain")

        # Construct the payload format required by Strapi REST API
        payload = {
            "data": {
                "type": key,
                "subject": subject,
                "html": html_content,
                "plain": plain_content
            }
        }

        try:
            response = requests.post(endpoint, json=payload, headers=headers)
            
            if response.status_code in [200, 201]:
                print(f"Successfully added entry for type: {key}")
            else:
                print(f"Failed to add '{key}'. Status: {response.status_code}, Response: {response.text}")
                
        except Exception as e:
            print(f"An error occurred while connecting to Strapi for key '{key}': {e}")

if __name__ == "__main__":
    import_emails()