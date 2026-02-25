import json
f = json.load(open('data/market_signals/finnhub_2026-02-24.json', encoding='utf-8'))
print("Top-level keys:", list(f.keys()))
for k in f.keys():
    v = f[k]
    if isinstance(v, list) and v:
        print(f"\n{k}: {len(v)} items, sample keys: {list(v[0].keys()) if isinstance(v[0], dict) else type(v[0])}")
        if isinstance(v[0], dict) and len(v) > 0:
            print(f"  sample: {json.dumps(v[0], ensure_ascii=False)[:200]}")
    elif isinstance(v, dict):
        print(f"\n{k}: dict with keys {list(v.keys())[:10]}")
    else:
        print(f"\n{k}: {type(v).__name__} = {str(v)[:100]}")
