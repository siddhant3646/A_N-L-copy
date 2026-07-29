import json
import shutil
from pathlib import Path

CONFIG_PATH = Path("config/qa_patterns.json")
PAYLOAD_PATH = Path("new_patterns_payload.json")

# Load main config
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# Load new patterns payload
with open(PAYLOAD_PATH, "r", encoding="utf-8") as f:
    payload = json.load(f)

# Backup original
shutil.copy(CONFIG_PATH, CONFIG_PATH.with_suffix(".json.bak"))

# Merge new patterns into data["patterns"]
existing_keys = set(data["patterns"].keys())
new_keys = set(payload["patterns"].keys())
conflicts = existing_keys & new_keys
if conflicts:
    print(f"Warning: skipping already existing pattern keys: {conflicts}")

for key, value in payload["patterns"].items():
    if key not in existing_keys:
        data["patterns"][key] = value

# Merge new category metadata into data["categories"]
for key, value in payload.get("categories", {}).items():
    if key not in data["categories"]:
        data["categories"][key] = value
        print(f"Added new category metadata: {key}")
    else:
        print(f"Category metadata already exists: {key}")

# Write back with compact but readable formatting
with open(CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Done. Total patterns now: {len(data['patterns'])}")
