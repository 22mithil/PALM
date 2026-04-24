import json
import time
import os
from pinecone import Pinecone, ServerlessSpec

# Configuration
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "pcsk_5KNLfS_QeXCssj3b6Qbd6waJ8WyiAFKQRYiWw65pu5yamznSCTN1Hpuw8qkRMjwZN9sDxp")  # Replace "pc" with your actual key if needed
PINECONE_INDEX_NAME = "palm-fyp"
PINECONE_ENVIRONMENT = "us-east-1"
JSON_FILE = "chunks_v2.json"

def main():
    print(f"Loading data from {JSON_FILE}...")
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            chunks = json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {JSON_FILE}. Make sure the file exists in the current directory.")
        return
    
    print(f"Loaded {len(chunks)} chunks.")
    
    # Initialize Pinecone
    print("Connecting to Pinecone...")
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
    except Exception as e:
        print(f"Failed to connect to Pinecone. Is your API key correct? Error: {e}")
        return
    
    # Check if index exists, create if not
    try:
        existing_indexes = [index.name for index in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing_indexes:
            print(f"Creating index '{PINECONE_INDEX_NAME}' (1536 dimensions)...")
            pc.create_index(
                name=PINECONE_INDEX_NAME, 
                dimension=1536, 
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=PINECONE_ENVIRONMENT)
            )
            # Wait for index to be initialized
            time.sleep(10)
        else:
            print(f"Index '{PINECONE_INDEX_NAME}' already exists.")
    except Exception as e:
        print(f"Error checking/creating Pinecone index: {e}")
        return
        
    index = pc.Index(PINECONE_INDEX_NAME)
    
    # Delete existing records
    print("Deleting existing records from index...")
    try:
        index.delete(delete_all=True)
        print("Successfully deleted existing records.")
        time.sleep(5) # Wait for deletion to propagate
    except Exception as e:
        print(f"Error deleting records: {e}")
        # Note: Some older Pinecone client versions or specific setups might not support delete_all without a namespace.
        # If this fails, we'll continue anyway, but it's good to print the warning.
        
    # Prepare records
    print("Preparing records for upsert...")
    records = []
    skipped = 0
    for chunk in chunks:
        # Skip if no embedding is present (e.g., if there was an error generating it)
        if not chunk.get("embedding"):
            skipped += 1
            continue
            
        record = {
            "id": chunk["chunk_id"],
            "values": [float(v) for v in chunk["embedding"]],
            "metadata": {
                "text": chunk.get("text", "")[:1500],
                "chunk_type": chunk.get("chunk_type", ""),
                "grade": chunk.get("grade", 0),
                "subject": chunk.get("subject", ""),
                "chapter_id": chunk.get("chapter_id", ""),
                "topic": chunk.get("topic", ""),
                "section_title": chunk.get("section_title", ""),
                "difficulty": chunk.get("difficulty", 1),
                "topic_tags": ",".join(chunk.get("topic_tags", [])),
                "page_range": chunk.get("page_range", ""),
                "source_file": chunk.get("source_file", ""),
            }
        }
        records.append(record)
        
    if skipped > 0:
        print(f"⚠️ Skipped {skipped} chunks because they did not have embeddings.")
        
    if not records:
        print("No valid records to upsert. Exiting.")
        return
        
    print(f"Upserting {len(records)} records in batches of 100...")
    for i in range(0, len(records), 100):
        batch = records[i:i+100]
        try:
            index.upsert(vectors=batch)
            print(f"  Upserted {min(i+100, len(records))}/{len(records)}")
            time.sleep(0.2)
        except Exception as e:
            print(f"Error during upsert: {e}")
            break
        
    print("\n✅ Upsert Complete!")
    try:
        print(f"Pinecone Stats: {index.describe_index_stats()}")
    except Exception as e:
        print(f"Could not retrieve index stats: {e}")

if __name__ == "__main__":
    main()
