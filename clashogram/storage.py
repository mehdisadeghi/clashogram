########################################################################
# Persistence
########################################################################
import json
import shelve
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sent (
    war_id TEXT NOT NULL,
    msg_id TEXT NOT NULL,
    PRIMARY KEY (war_id, msg_id)
);
CREATE TABLE IF NOT EXISTS archive (
    war_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS war (
    war_tag TEXT PRIMARY KEY,
    clan_tag TEXT NOT NULL,
    opponent_tag TEXT NOT NULL,
    payload TEXT
);
"""


class Storage:
    """Remembers which messages a war has already produced."""

    def __init__(self, path):
        self._db = sqlite3.connect(path)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.executescript(SCHEMA)
        self._db.commit()

    def is_sent(self, war_id, msg_id):
        row = self._db.execute(
            'SELECT 1 FROM sent WHERE war_id = ? AND msg_id = ?',
            (war_id, msg_id)).fetchone()
        return row is not None

    def mark_sent(self, war_id, msg_id):
        self._db.execute(
            'INSERT OR IGNORE INTO sent (war_id, msg_id) VALUES (?, ?)',
            (war_id, msg_id))
        self._db.commit()

    def remember_war(self, war_tag, payload, keep_payload):
        """Note a league war, keeping the war itself once it has ended.

        The payload is only worth keeping once the war is over and can
        no longer move. Until then only the two clans are recorded."""
        self._db.execute(
            'INSERT INTO war (war_tag, clan_tag, opponent_tag, payload) '
            'VALUES (?, ?, ?, ?) '
            'ON CONFLICT(war_tag) DO UPDATE SET payload = excluded.payload',
            (war_tag, payload['clan']['tag'], payload['opponent']['tag'],
             json.dumps(payload) if keep_payload else None))
        self._db.commit()

    def archive_war(self, war_id, payload):
        """Keep a finished war so later seasons can be recomputed."""
        self._db.execute(
            'INSERT OR REPLACE INTO archive (war_id, payload) VALUES (?, ?)',
            (war_id, json.dumps(payload, ensure_ascii=False)))
        self._db.commit()

    def archived_wars(self):
        for war_id, payload in self._db.execute(
                'SELECT war_id, payload FROM archive ORDER BY war_id'):
            yield war_id, json.loads(payload)

    def finished_war(self, war_tag):
        row = self._db.execute(
            'SELECT payload FROM war WHERE war_tag = ?', (war_tag,)).fetchone()
        if row is None or row[0] is None:
            return None
        return json.loads(row[0])

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def import_shelve(path, storage):
    """Carry an old shelve warlog over so wars are not announced twice.

    The shelve only ever held `{war_id: {msg_id: True}}`, so this is all
    there is to take. Note the dbm backend is chosen at write time and is
    not portable, which usually means running this where the file was
    written rather than on a different machine."""
    imported = 0
    with shelve.open(path, flag='r') as old:
        for war_id, messages in old.items():
            for msg_id, was_sent in messages.items():
                if was_sent:
                    storage.mark_sent(war_id, msg_id)
                    imported += 1
    return imported
