import json

files = ["content.json", "structure.json", "resources.json"]
found_types = set()

for f_name in files:
    try:
        with open(f_name, "r", encoding="utf-8") as f:
            data = json.load(f)
            for route, blocks in data.items():
                if isinstance(blocks, list):
                    for b in blocks:
                        if isinstance(b, dict):
                            if b.get("type") == "container":
                                for inner in b.get("content", []):
                                    if isinstance(inner, dict):
                                        found_types.add(inner.get("type"))
                            else:
                                found_types.add(b.get("type"))
    except FileNotFoundError:
        print(f"Skipping {f_name} (Not found)")

print("\n🔍 Unique Block Types Found in Your JSON Files:")
for t in sorted(list(found_types)):
    print(f" - {t}")