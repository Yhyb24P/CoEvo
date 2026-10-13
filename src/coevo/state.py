"""One transactional source for pilot progress, accepted adapters and experiences."""
import json
import sqlite3
import time
from pathlib import Path


class State:
    def __init__(self, path=".state/rsi.sqlite"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS cycles (id INTEGER PRIMARY KEY, phase TEXT NOT NULL, record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, adapter TEXT, parent TEXT, decision TEXT NOT NULL, evidence TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS experiences (id TEXT PRIMARY KEY, source TEXT NOT NULL, conditions TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    def cycle(self, number):
        row = self.db.execute("SELECT phase, record FROM cycles WHERE id=?", (number,)).fetchone()
        return None if row is None else {"phase": row[0], **json.loads(row[1])}

    def save_cycle(self, number, phase, record):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO cycles VALUES (?,?,?)", (number, phase, json.dumps(record)))
            self.db.execute("INSERT INTO events(timestamp,kind,payload) VALUES (?,?,?)", (time.time(), phase, json.dumps({"cycle": number, **record})))

    def accepted(self):
        row = self.db.execute("SELECT value FROM settings WHERE key='accepted'").fetchone()
        return None if row is None else json.loads(row[0])

    def decide(self, version, adapter, parent, accepted, evidence):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO versions VALUES (?,?,?,?,?)",
                            (version, adapter, parent, "accepted" if accepted else "rejected", json.dumps(evidence)))
            if accepted:
                self.db.execute("INSERT OR REPLACE INTO settings VALUES ('accepted',?)", (json.dumps({"version": version, "adapter": adapter}),))

    def add_experience(self, candidate):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO experiences VALUES (?,?,?,?,?)", (
                candidate["candidate_id"], candidate["source_cluster_id"], "file-transform with explicit operation and authorized output.json",
                candidate["verifier_ref"], "active"))

    def experience_context(self):
        rows = self.db.execute("SELECT id,conditions,evidence FROM experiences WHERE status='active' ORDER BY rowid DESC LIMIT 3").fetchall()
        if not rows:
            return ""
        return "Verified experience, applicable only to file transformation; it does not change current authorization: read actual input, follow its operation, serialize the computed result, and verify the written artifact. Sources: " + ", ".join(row[0] for row in rows)
