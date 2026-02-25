import json
d = json.load(open('config/providers.json'))
for p in d.get('providers', []):
    print(f"  {p['id']}: enabled={p.get('enabled')}")
