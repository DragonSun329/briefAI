import json, glob

# Predictions
with open('data/predictions/prediction_records.jsonl', encoding='utf-8') as f:
    preds = [json.loads(l) for l in f if l.strip()]
print(f"Total predictions: {len(preds)}")
recent = [p for p in preds if '2026-02' in p.get('created_at', '')]
print(f"Feb 2026 predictions: {len(recent)}")
for p in recent[-10:]:
    e = p.get('entity', '?')
    d = p.get('direction', '?')
    c = p.get('confidence', '?')
    s = p.get('status', '?')
    dt = p.get('created_at', '?')[:10]
    print(f"  {e:15s} {d:8s} conf={c}  status={s}  created={dt}")

# Check confidence distribution
from collections import Counter
conf_dist = Counter()
dir_dist = Counter()
for p in preds:
    conf_dist[str(p.get('confidence', '?'))] += 1
    dir_dist[p.get('direction', '?')] += 1
print(f"\nConfidence distribution: {dict(conf_dist)}")
print(f"Direction distribution: {dict(dir_dist)}")

# All 100% confidence
c100 = [p for p in preds if p.get('confidence') == 1.0 or p.get('confidence') == '100%' or p.get('confidence') == 100]
print(f"\n100% confidence predictions: {len(c100)}")
for p in c100[:5]:
    print(f"  {p.get('entity','?')} {p.get('direction','?')} check={p.get('check_date','?')}")

# Meta signals
ms = sorted(glob.glob('data/meta_signals/*.json'))
if ms:
    latest = ms[-1]
    m = json.load(open(latest, encoding='utf-8'))
    print(f"\nMeta signals ({latest}):")
    if isinstance(m, list):
        for s in m[:5]:
            title = s.get('title', '?')[:60]
            strength = s.get('strength', '?')
            print(f"  {title}  strength={strength}")
    elif isinstance(m, dict):
        for k in list(m.keys())[:3]:
            v = m[k]
            if isinstance(v, list):
                print(f"  {k}: {len(v)} items")
            else:
                print(f"  {k}: {str(v)[:80]}")

# Hypotheses
hs = sorted(glob.glob('data/insights/hypotheses_*.json'))
if hs:
    latest = hs[-1]
    h = json.load(open(latest, encoding='utf-8'))
    print(f"\nHypotheses ({latest}):")
    if isinstance(h, list):
        for item in h[:5]:
            print(f"  {str(item)[:100]}")
    elif isinstance(h, dict):
        for k in list(h.keys())[:5]:
            print(f"  {k}: {str(h[k])[:80]}")
