"""One transactional source for pilot progress, accepted adapters and experiences."""
import json
import re
import sqlite3
import time
from pathlib import Path


class State:
    def __init__(self, path=".state/rsi.sqlite"):
        self.path = str(Path(path).resolve())
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS cycles (id INTEGER PRIMARY KEY, phase TEXT NOT NULL, record TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, adapter TEXT, parent TEXT, decision TEXT NOT NULL, evidence TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS experiences (id TEXT PRIMARY KEY, source TEXT NOT NULL, conditions TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
        ''')

    @classmethod
    def for_experiment(cls, config):
        """Bind one explicit database to one study/stream/arm; never adopt old state."""
        namespace = {key: config.get(key) for key in ('study_id', 'stream_id', 'arm_id')}
        for key, value in namespace.items():
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', value) or '..' in value:
                raise ValueError(f'Explicit valid {key} is required for experiment state')
        template = config.get('state_path')
        if not isinstance(template, str) or not template:
            raise ValueError('Explicit state_path is required for experiment state')
        state = cls(template.format(**namespace))
        try:
            with state.db:
                # Lock before checking, so competing namespaces cannot both bind.
                state.db.execute('BEGIN IMMEDIATE')
                row = state.db.execute("SELECT value FROM settings WHERE key='experiment_namespace'").fetchone()
                if row:
                    if json.loads(row[0]) != namespace:
                        raise ValueError('State database belongs to another experiment namespace')
                else:
                    occupied = any(state.db.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone()
                                   for table in ('cycles', 'versions', 'settings', 'experiences', 'events'))
                    if occupied:
                        raise ValueError('Existing unscoped state must not be adopted by a new experiment')
                    state.db.execute("INSERT INTO settings VALUES ('experiment_namespace',?)", (json.dumps(namespace),))
            state.namespace = namespace
            return state
        except BaseException:
            state.db.close()
            raise

    def manifest(self):
        return {'state_path': self.path, 'namespace': self.namespace}

    def close(self):
        self.db.close()

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
