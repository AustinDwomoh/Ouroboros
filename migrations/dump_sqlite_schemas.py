"""Dump schema (tables + columns) for all SQLite .db files in the data/ directory.

Usage: run from project root with the project's Python.
"""
import os
import glob
import sqlite3
import json

DATA_DIR = os.getenv("SQLITE_DATA_DIR", "data")

def inspect_db(path):
    out = {"file": path, "tables": {}}
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY name")
    for name, typ in cur.fetchall():
        # skip sqlite internal
        if name.startswith('sqlite_'):
            continue
        try:
            cur.execute(f"PRAGMA table_info('{name}')")
            cols = []
            for cid, colname, coltype, notnull, dflt_value, pk in cur.fetchall():
                cols.append({
                    "cid": cid,
                    "name": colname,
                    "type": coltype,
                    "notnull": bool(notnull),
                    "default": dflt_value,
                    "pk": bool(pk),
                })
            out["tables"][name] = {"type": typ, "columns": cols}
        except Exception as e:
            out["tables"][name] = {"type": typ, "error": str(e)}
    conn.close()
    return out

def main():
    db_files = sorted(glob.glob(os.path.join(DATA_DIR, "*.db")))
    if not db_files:
        print("No .db files found in data/ (or SQLITE_DATA_DIR).")
        return
    results = []
    for db in db_files:
        print(f"Inspecting: {db}")
        res = inspect_db(db)
        results.append(res)
        # pretty print
        for tname, tinfo in res["tables"].items():
            print(f"  Table: {tname} ({tinfo.get('type')})")
            if "error" in tinfo:
                print(f"    Error: {tinfo['error']}")
                continue
            for c in tinfo["columns"]:
                print(f"    - {c['name']} {c['type']} notnull={c['notnull']} pk={c['pk']} default={c['default']}")
        print()

    # Also write a JSON summary to migrations/sqlite_schemas.json
    out_path = os.path.join("migrations", "sqlite_schemas.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Wrote JSON summary to {out_path}")

if __name__ == '__main__':
    main()
