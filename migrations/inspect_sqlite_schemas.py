import sqlite3
import os
import json

SQLITE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_FILES = [
    'serverstats.db',
    'notifications_records.db',
    'leveling.db',
    'game_records.db',
    'finance.db',
    'mediarecords.db',
]

result = {}
for fn in DB_FILES:
    path = os.path.abspath(os.path.join(SQLITE_DIR, fn))
    info = {'exists': os.path.exists(path), 'tables': {}}
    if os.path.exists(path):
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            try:
                cur.execute(f"PRAGMA table_info('{t}')")
                cols = cur.fetchall()
                info['tables'][t] = [{'cid': c[0], 'name': c[1], 'type': c[2], 'notnull': c[3], 'dflt_value': c[4], 'pk': c[5]} for c in cols]
            except Exception as e:
                info['tables'][t] = {'error': str(e)}
        conn.close()
    result[fn] = info

print(json.dumps(result, indent=2))
