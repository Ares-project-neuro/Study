"""Local single-user persistence. Never store AI credentials here."""
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def root():
    path = Path(os.environ.get('STUDY_DATA_DIR', '.data')).resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


@contextmanager
def connect():
    db = sqlite3.connect(root() / 'study.sqlite3', timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL)')
    try:
        yield db
        db.commit()
    finally:
        db.close()


def save(kind, data, db=None):
    data = dict(data)
    data.setdefault('id', uuid.uuid4().hex)
    data.setdefault('created_at', now())
    data['updated_at'] = now()
    if db is None:
        with connect() as conn:
            return save(kind, data, conn)
    db.execute('INSERT INTO items VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
               (data['id'], kind, json.dumps(data, ensure_ascii=False)))
    return data


def get(kind, ident, db=None):
    if db is None:
        with connect() as conn:
            return get(kind, ident, conn)
    row = db.execute('SELECT data FROM items WHERE id=? AND kind=?', (ident, kind)).fetchone()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(404, 'Elemento non trovato')
    return json.loads(row[0])


def all_items(kind, db=None):
    if db is None:
        with connect() as conn:
            return all_items(kind, conn)
    return [json.loads(r[0]) for r in db.execute('SELECT data FROM items WHERE kind=? ORDER BY rowid DESC', (kind,))]


def delete(kind, ident):
    with connect() as db:
        db.execute('DELETE FROM items WHERE kind=? AND id=?', (kind, ident))
