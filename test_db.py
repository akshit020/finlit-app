import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print("URL:", SUPABASE_URL)
print("KEY starts with:", SUPABASE_KEY[:20] if SUPABASE_KEY else "MISSING")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

TABLE_URL = f"{SUPABASE_URL}/rest/v1/kv_store"

# Test 1 - read
res = requests.get(TABLE_URL, headers=HEADERS, params={"select": "key,value"})
print("Read status:", res.status_code)
print("Read response:", res.text[:200])

# Test 2 - patch
res2 = requests.patch(
    TABLE_URL,
    headers={**HEADERS, "Prefer": "return=representation"},
    params={"key": "eq.users"},
    json={"value": {"test": "hello"}}
)
print("Patch status:", res2.status_code)
print("Patch response:", res2.text[:200])