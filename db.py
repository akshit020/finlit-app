import os
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

TABLE_URL = f"{SUPABASE_URL}/rest/v1/kv_store"

def load_json(path):
    key = os.path.basename(path).replace(".json", "")
    try:
        res = requests.get(
            TABLE_URL,
            headers={**HEADERS, "Accept": "application/json"},
            params={"key": f"eq.{key}", "select": "value"}
        )
        data = res.json()
        if data and len(data) > 0:
            return data[0]["value"]
        return {}
    except Exception as e:
        print(f"DB load error for {key}:", e)
        return {}

def save_json(path, data):
    key = os.path.basename(path).replace(".json", "")
    try:
        check = requests.get(
            TABLE_URL,
            headers={**HEADERS, "Accept": "application/json"},
            params={"key": f"eq.{key}", "select": "key"}
        )
        exists = check.json()
        if exists and len(exists) > 0:
            requests.patch(
                TABLE_URL,
                headers={**HEADERS, "Prefer": "return=minimal"},
                params={"key": f"eq.{key}"},
                json={"value": data}
            )
        else:
            requests.post(
                TABLE_URL,
                headers={**HEADERS, "Prefer": "return=minimal"},
                json={"key": key, "value": data}
            )
    except Exception as e:
        print(f"DB save error for {key}:", e)
