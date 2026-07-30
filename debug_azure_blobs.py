import os
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

load_dotenv()

AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
# Set container to 'content' and target 'resourceblobs/' prefix
CONTAINER_NAME = "content"

def debug_inspect_resourceblobs():
    if not AZURE_CONN_STR:
        print("❌ Error: AZURE_STORAGE_CONNECTION_STRING is missing from your .env file.")
        return

    print(f"☁️ Connecting to Azure Container: '{CONTAINER_NAME}' (folder: resourceblobs/)...")
    
    try:
        service_client = BlobServiceClient.from_connection_string(AZURE_CONN_STR)
        container_client = service_client.get_container_client(CONTAINER_NAME)
        
        blobs = container_client.list_blobs(name_starts_with="resourceblobs/")
        
        count = 0
        image_count = 0
        for blob in blobs:
            count += 1
            props = container_client.get_blob_client(blob.name).get_blob_properties()
            content_type = props.content_settings.content_type
            print(f"[{count}] Name: {blob.name} | Type: {content_type} | Size: {blob.size} bytes")
            
            if content_type and content_type.startswith("image/"):
                image_count += 1
            elif blob.name.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif')):
                image_count += 1

        print(f"\n✨ Found {count} total items in 'resourceblobs/', with {image_count} identified as images.")

    except Exception as e:
        print(f"❌ Failed to inspect blobs: {e}")

if __name__ == "__main__":
    debug_inspect_resourceblobs()