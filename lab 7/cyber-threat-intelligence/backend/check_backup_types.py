import json
import pathlib
import collections

backup = pathlib.Path(
    "../backups/cyber_threat_intel_20261118_222501"
)

types = collections.Counter()

for file in backup.glob("*.json"):
    if file.name.endswith("_indexes.json"):
        continue

    if file.name == "manifest.json":
        continue

    content = file.read_text(encoding="utf-8")
    data = json.loads(content)

    def find_types(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.startswith("$"):
                    types[key] += 1
                find_types(item)
        elif isinstance(value, list):
            for item in value:
                find_types(item)

    find_types(data)

print("Extended JSON types found:")
for name, count in sorted(types.items()):
    print(name, count)