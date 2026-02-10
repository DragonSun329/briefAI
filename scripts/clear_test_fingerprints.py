# Clear test fingerprints
import sqlite3
conn = sqlite3.connect('data/signals.db')
c = conn.cursor()
c.execute("DELETE FROM signal_fingerprints WHERE entity_id LIKE 'test_%'")
print(f'Cleared {c.rowcount} test fingerprints')
conn.commit()
conn.close()
