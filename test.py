import json

with open("firebase-key.json") as f:
    print(json.dumps(json.load(f), indent=2))
