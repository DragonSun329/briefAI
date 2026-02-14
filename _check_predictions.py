import sqlite3
conn = sqlite3.connect('data/predictions.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT entity_name, confidence, horizon_date, predicted_outcome FROM predictions WHERE status='pending' ORDER BY confidence DESC LIMIT 15").fetchall()
for r in rows:
    print(f"{r['confidence']:.2f} | {r['entity_name']:20s} | {r['horizon_date']} | {str(r['predicted_outcome'])[:50]}")
conn.close()
