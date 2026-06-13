import json
from db import save_json

with open("data/users.json") as f:
    save_json("data/users.json", json.load(f))
print("Users migrated")

with open("data/trades.json") as f:
    save_json("data/trades.json", json.load(f))
print("Trades migrated")

with open("data/pending_orders.json") as f:
    save_json("data/pending_orders.json", json.load(f))
print("Pending orders migrated")
