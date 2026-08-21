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
    chat_id TEXT NOT NULL,
    PRIMARY KEY (war_id, msg_id, chat_id)
);
CREATE TABLE IF NOT EXISTS subscription (
    clan_tag TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    added_at TEXT NOT NULL,
    PRIMARY KEY (clan_tag, chat_id)
);
CREATE TABLE IF NOT EXISTS operator (
    user_id TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clan_tag TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    requester_id TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    state TEXT NOT NULL
);
-- A partial index, because sqlite has no inline UNIQUE ... WHERE. One
-- request may be pending per chat and clan; resolved ones stay as history.
CREATE UNIQUE INDEX IF NOT EXISTS request_pending
    ON request (clan_tag, chat_id) WHERE state = 'pending';
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

    def __init__(self, path, bootstrap_chat_id=None):
        self._db = sqlite3.connect(path)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._migrate_sent(bootstrap_chat_id)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def _migrate_sent(self, bootstrap_chat_id):
        """Give an old `sent` table its chat column.

        Rows written before delivery was recorded per chat can only have
        gone to the bootstrap chat. Without one they cannot be attributed,
        and a wrong guess silences a real chat forever, so they go."""
        columns = [row[1] for row in
                   self._db.execute('PRAGMA table_info(sent)')]
        if not columns or 'chat_id' in columns:
            return
        self._db.executescript("""
            ALTER TABLE sent RENAME TO sent_old;
            CREATE TABLE sent (
                war_id TEXT NOT NULL,
                msg_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                PRIMARY KEY (war_id, msg_id, chat_id)
            );
        """)
        if bootstrap_chat_id is not None:
            self._db.execute(
                'INSERT INTO sent (war_id, msg_id, chat_id) '
                'SELECT war_id, msg_id, ? FROM sent_old',
                (str(bootstrap_chat_id),))
        self._db.executescript('DROP TABLE sent_old;')
        self._db.commit()

    def is_sent(self, war_id, msg_id, chat_id):
        row = self._db.execute(
            'SELECT 1 FROM sent '
            'WHERE war_id = ? AND msg_id = ? AND chat_id = ?',
            (war_id, msg_id, str(chat_id))).fetchone()
        return row is not None

    def mark_sent(self, war_id, msg_id, chat_id):
        self._db.execute(
            'INSERT OR IGNORE INTO sent (war_id, msg_id, chat_id) '
            'VALUES (?, ?, ?)',
            (war_id, msg_id, str(chat_id)))
        self._db.commit()

    def sent_msg_ids(self, war_id, chat_id):
        return [row[0] for row in self._db.execute(
            'SELECT msg_id FROM sent WHERE war_id = ? AND chat_id = ?',
            (war_id, str(chat_id)))]

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

    def subscriptions(self):
        return [(clan_tag, chat_id) for clan_tag, chat_id in self._db.execute(
            'SELECT clan_tag, chat_id FROM subscription '
            'ORDER BY clan_tag, chat_id')]

    def subscribe(self, clan_tag, chat_id, added_at):
        self._db.execute(
            'INSERT OR IGNORE INTO subscription (clan_tag, chat_id, added_at) '
            'VALUES (?, ?, ?)', (clan_tag, str(chat_id), added_at))
        self._db.commit()

    def unsubscribe(self, clan_tag, chat_id):
        cursor = self._db.execute(
            'DELETE FROM subscription WHERE clan_tag = ? AND chat_id = ?',
            (clan_tag, str(chat_id)))
        self._db.commit()
        return cursor.rowcount

    def operators(self):
        return [row[0] for row in self._db.execute(
            'SELECT user_id FROM operator ORDER BY user_id')]

    def add_operator(self, user_id, added_at):
        self._db.execute(
            'INSERT OR IGNORE INTO operator (user_id, added_at) '
            'VALUES (?, ?)', (str(user_id), added_at))
        self._db.commit()

    def remove_operator(self, user_id):
        cursor = self._db.execute('DELETE FROM operator WHERE user_id = ?',
                                  (str(user_id),))
        self._db.commit()
        return cursor.rowcount

    def forget_chat(self, chat_id):
        """Stop following everything in one chat. Used when the bot is
        removed from it, since posting there can only fail afterwards."""
        cursor = self._db.execute(
            'DELETE FROM subscription WHERE chat_id = ?', (str(chat_id),))
        self._db.commit()
        return cursor.rowcount

    def file_request(self, clan_tag, chat_id, requester_id, requested_at):
        """Record a pending request, or None if one is already pending."""
        try:
            cursor = self._db.execute(
                'INSERT INTO request (clan_tag, chat_id, requester_id, '
                'requested_at, state) VALUES (?, ?, ?, ?, ?)',
                (clan_tag, str(chat_id), str(requester_id), requested_at,
                 'pending'))
        except sqlite3.IntegrityError:
            return None
        self._db.commit()
        return cursor.lastrowid

    def pending_requests(self):
        return [dict(zip(('id', 'clan_tag', 'chat_id', 'requester_id'), row))
                for row in self._db.execute(
                    'SELECT id, clan_tag, chat_id, requester_id FROM request '
                    "WHERE state = 'pending' ORDER BY id")]

    def resolve_request(self, request_id, state):
        """Mark one pending request, returning it, or None if there is none."""
        row = self._db.execute(
            'SELECT clan_tag, chat_id FROM request '
            "WHERE id = ? AND state = 'pending'", (request_id,)).fetchone()
        if row is None:
            return None
        self._db.execute('UPDATE request SET state = ? WHERE id = ?',
                         (state, request_id))
        self._db.commit()
        return {'id': request_id, 'clan_tag': row[0], 'chat_id': row[1]}

    def close(self):
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def import_shelve(path, storage, chat_id):
    """Carry an old shelve warlog over so wars are not announced twice.

    The shelve only ever held `{war_id: {msg_id: True}}`, so this is all
    there is to take, and the chat it was sent to has to be supplied. Note
    the dbm backend is chosen at write time and is not portable, which
    usually means running this where the file was written rather than on a
    different machine."""
    imported = 0
    with shelve.open(path, flag='r') as old:
        for war_id, messages in old.items():
            for msg_id, was_sent in messages.items():
                if was_sent:
                    storage.mark_sent(war_id, msg_id, chat_id)
                    imported += 1
    return imported
