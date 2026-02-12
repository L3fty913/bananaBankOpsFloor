#!/usr/bin/env python3
import sqlite3
from pathlib import Path
import time

BASE = Path('/opt/polybot')
DB_DIR = BASE / 'rag'
DB_DIR.mkdir(parents=True, exist_ok=True)
DB = DB_DIR / 'knowledge.db'

paths = [
    BASE / 'rag_sources',
]

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS docs (id INTEGER PRIMARY KEY, path TEXT UNIQUE, content TEXT, updated_at INTEGER)')
cur.execute('CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(path, content, content="docs", content_rowid="id")')

inserted = 0
updated = 0
for p in paths:
    if not p.exists():
        continue
    for f in p.rglob('*'):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {'.md', '.txt', '.json'}:
            continue
        text = f.read_text(errors='ignore')
        ts = int(time.time())
        cur.execute('SELECT id FROM docs WHERE path=?', (str(f),))
        row = cur.fetchone()
        if row:
            cur.execute('UPDATE docs SET content=?, updated_at=? WHERE id=?', (text, ts, row[0]))
            cur.execute('INSERT INTO docs_fts(docs_fts, rowid, path, content) VALUES ("delete", ?, ?, ?)', (row[0], str(f), text))
            cur.execute('INSERT INTO docs_fts(rowid, path, content) VALUES (?, ?, ?)', (row[0], str(f), text))
            updated += 1
        else:
            cur.execute('INSERT INTO docs(path, content, updated_at) VALUES (?, ?, ?)', (str(f), text, ts))
            rid = cur.lastrowid
            cur.execute('INSERT INTO docs_fts(rowid, path, content) VALUES (?, ?, ?)', (rid, str(f), text))
            inserted += 1

conn.commit()
print({'db': str(DB), 'inserted': inserted, 'updated': updated})

# quick smoke query
q = 'prediction market liquidity spread order execution risk'
cur.execute('SELECT path, snippet(docs_fts, 1, "[", "]", "…", 12) FROM docs_fts WHERE docs_fts MATCH ? LIMIT 5', (q,))
rows = cur.fetchall()
print('sample_results', len(rows))
for r in rows:
    print('-', r[0])

conn.close()
