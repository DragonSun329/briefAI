import json

# Prediction records - look at actual structure
with open('data/predictions/prediction_records.jsonl', encoding='utf-8') as f:
    preds = [json.loads(l) for l in f if l.strip()]
if preds:
    print("=== PREDICTION RECORD STRUCTURE ===")
    print(json.dumps(preds[0], indent=2, ensure_ascii=False)[:1000])

# Meta signals detail
m = json.load(open('data/meta_signals/meta_signals_2026-02-24.json', encoding='utf-8'))
print("\n=== META SIGNALS ===")
signals = m.get('signals', m.get('meta_signals', []))
if isinstance(signals, list):
    for s in signals[:3]:
        print(json.dumps(s, indent=2, ensure_ascii=False)[:500])
        print("---")
else:
    print(f"Keys: {list(m.keys())}")
    # Try printing more
    for k in ['signals', 'meta_signals', 'themes', 'clusters']:
        if k in m:
            print(f"\n{k}: {json.dumps(m[k], ensure_ascii=False)[:800]}")

# Hypotheses detail
h = json.load(open('data/insights/hypotheses_2026-02-24.json', encoding='utf-8'))
print("\n=== HYPOTHESES ===")
bundles = h.get('bundles', [])
for b in bundles[:2]:
    print(f"Bundle: {b.get('concept_name', '?')}")
    for hyp in b.get('hypotheses', [])[:2]:
        print(f"  H: {hyp.get('statement', hyp.get('hypothesis', '?'))[:120]}")
        print(f"     mechanism: {hyp.get('mechanism', '?')[:80]}")
        print(f"     confidence: {hyp.get('confidence', '?')}")

# Validation - detailed view  
v = json.load(open('data/validation_results/validation_20260224_153059.json', encoding='utf-8'))
print("\n=== VALIDATION DETAIL ===")
for ent in v.get('top_validated', []):
    eid = ent.get('entity_id', '?')
    sig = ent.get('briefai_signal', {})
    mkt = ent.get('market_reality', {})
    val = ent.get('validation', {})
    print(f"{eid}: sentiment={sig.get('sentiment')}, momentum={sig.get('momentum')}")
    print(f"  price 1d={mkt.get('price_change_1d')} 5d={mkt.get('price_change_5d')} 20d={mkt.get('price_change_20d')}")
    print(f"  score={val.get('score')} grade={val.get('grade')} direction={val.get('direction_aligned')}")
