import json, glob

# Forecast ledger
ledgers = glob.glob('data/predictions/forecast_ledger*')
print('Ledger files:', ledgers)
for l in ledgers:
    with open(l, encoding='utf-8') as f:
        lines = [json.loads(x) for x in f if x.strip()]
    print(f"\n{l}: {len(lines)} entries")
    for e in lines[:5]:
        ent = e.get('entity', '?')
        d = e.get('expected_direction', '?')
        c = e.get('confidence_at_prediction', '?')
        m = e.get('canonical_metric', '?')
        dt = e.get('created_at', '?')[:10]
        print(f"  {ent:15s} dir={d:5s} conf={c}  metric={m}  date={dt}")

# The brief shows "Snowflake bullish 100%" etc - where does that come from?
# Check action predictions
aps = glob.glob('data/predictions/action_predictions*')
print(f"\nAction prediction files: {aps}")

# Check what the brief generator loads
import os
for root, dirs, files in os.walk('data/predictions'):
    for f in files:
        fp = os.path.join(root, f)
        sz = os.path.getsize(fp)
        print(f"  {fp} ({sz} bytes)")
