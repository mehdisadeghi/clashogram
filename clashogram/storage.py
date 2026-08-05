########################################################################
# Persistence
########################################################################
import shelve
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS sent (
    war_id TEXT NOT NULL,
    msg_id TEXT NOT NULL,
    PRIMARY KEY (war_id, msg_id)
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
