Multi-clan subscriptions operated over Telegram
===============================================

:Status: draft
:Date: 2026-08-21
:ADRs: `0008 <../adr/0008-the-bot-is-the-control-plane.rst>`_,
       `0009 <../adr/0009-keep-the-war-archive-off-by-default.rst>`_,
       `0010 <../adr/0010-key-sent-messages-by-chat.rst>`_

Goal
----

One process follows several clans and posts each to its own chats. The operator
adds and removes clans by talking to the bot. Anybody else may ask to be added
and can do nothing else.

Non-goals
---------

Per-clan language. The process renders every message in the locale it was
started with and this instance is ``fa_IR``. Deferred deliberately; see the
consequences in ADR 0008.

A public instance. Requests are refused unless the operator opens them, and
approving one is always a manual act.

Per-clan CoC tokens. War data is public and read only, so the instance token
covers every clan and no tenant supplies a credential.


Data model
----------

Three changes to ``storage.py``. All tables continue to be created with
``CREATE TABLE IF NOT EXISTS`` on open.

New, ``subscription``::

    clan_tag    TEXT NOT NULL
    chat_id     TEXT NOT NULL
    added_at    TEXT NOT NULL
    PRIMARY KEY (clan_tag, chat_id)

New, ``operator``::

    user_id  TEXT PRIMARY KEY
    added_at TEXT NOT NULL

New, ``request``::

    id           INTEGER PRIMARY KEY AUTOINCREMENT
    clan_tag     TEXT NOT NULL
    chat_id      TEXT NOT NULL
    requester_id TEXT NOT NULL
    requested_at TEXT NOT NULL
    state        TEXT NOT NULL      -- pending | approved | denied

with one pending request per chat and clan, and resolved ones kept as history::

    CREATE UNIQUE INDEX IF NOT EXISTS request_pending
        ON request (clan_tag, chat_id) WHERE state = 'pending';

A partial index, not a table constraint: SQLite rejects ``UNIQUE (...) WHERE
...`` inline.

Changed, ``sent``: gains ``chat_id TEXT NOT NULL`` and is keyed on
``(war_id, msg_id, chat_id)``.

Migration runs once on open, guarded by inspecting ``PRAGMA table_info(sent)``.
If ``chat_id`` is absent the table is rebuilt and existing rows take the
bootstrap chat id, which per ADR 0010 is the only chat they can have been sent
to. If no bootstrap chat id is configured the rows are dropped, because they
cannot be attributed and a wrong attribution silences a real chat.


Configuration
-------------

New options on ``clashogram``. Each reads an environment variable, which is how
Kubernetes supplies it.

``--admin-id`` / ``TELEGRAM_ADMIN_ID``
    Numeric Telegram user id of the operator. Without it no subscription can be
    changed at runtime and the instance is limited to its bootstrap pair.

``--archive`` / ``ARCHIVE``
    Off by default. Gates ``archive_war`` only, per ADR 0009.

``--open-requests`` / ``OPEN_REQUESTS``
    Off by default. When off, ``/request`` is answered with a refusal and no row
    is written.

Changed options:

``--clan-tag`` and ``--chat-id`` lose ``prompt=True`` and default to ``None``.
Given together they ensure one ``subscription`` row at startup, idempotently.
Given singly is a usage error. Given neither, the instance serves whatever the
warlog already holds.

Kubernetes: ``TELEGRAM_ADMIN_ID`` joins the secret, ``ARCHIVE`` and
``OPEN_REQUESTS`` join it alongside ``LANGUAGE`` and ``COC_CLAN_TAG``. Those
last are not secret and neither are these; the deployment reads one
``envFrom.secretRef`` and splitting non-secret config into a ``ConfigMap`` is
worth doing but is not part of this change.


Command surface
---------------

Owner only, recognised by ``from.id`` matching ``--admin-id``:

``/operators``
    The owner, then everybody they have named.
``/addoperator <user id>`` / ``/removeoperator <user id>``
    Name somebody to help, or stop. The owner is refused for both, so the
    seat cannot be given away or lost.

Operator, meaning the owner or anybody in ``operator``, accepted in any chat:

``/clans``
    Every subscription, grouped by clan, with the chat titles.
``/add <clan tag> [chat id]``
    Subscribe. The chat id defaults to the chat the command was sent in.
    Backfills ``sent`` for a war in progress, per ADR 0010.
``/remove <clan tag> [chat id]``
    Unsubscribe. Leaves ``sent`` rows alone.
``/requests``
    Pending requests with their ids.
``/approve <id>`` / ``/deny <id>``
    Resolve one. Approving subscribes and notifies the requesting chat.

Anyone, in any chat, because a channel post has no author to check:

``/start`` / ``/help``
    What the bot is, what this chat follows, and what may be asked of it.
    Telegram sends ``/start`` itself from the button it shows on first
    contact, so it is the one command that has to answer for the bot rather
    than fall through to "unknown command". Both render the same text, built
    per chat: the war commands appear only where a clan is followed, the
    request line only where requests are open, and the operator section only
    to the operator, who is not told to ask themselves.

``/chatid``
    The chat's own id, with the ``/add`` line to paste into a direct
    message. It reveals only what everybody in that chat already has.

Anyone, in the chat they want served:

``/request <clan tag>``
    Files a pending row and notifies the operator. Refused when
    ``--open-requests`` is off. Never grants anything.

Existing commands (``/war``, ``/missing``, ``/standings``, ``/stats``,
``/clan``) answer for the clans subscribed to the chat they were
asked in. One clan answers plainly; several prefix each answer with the clan
name. An unsubscribed chat gets only ``/help``, ``/chatid`` and ``/request``.

``TelegramNotifier.receive`` currently reads ``update['message']`` only, so
commands sent in a channel are silently ignored. It must also read
``channel_post``, and must surface ``from.id`` so the operator can be
recognised. Channel posts carry no ``from``, so operator commands are not
accepted in channels and belong in a direct message.

It also yields ``my_chat_member``, which ``getUpdates`` delivers by default
unlike ``chat_member`` for other people. Being added to a chat tells the
operator its id unasked, which is what makes a channel usable without hunting
for one; being removed drops that chat's subscriptions, since posting there can
only fail afterwards. ``receive`` therefore yields typed events, ``Command`` or
``Membership``, rather than a bare tuple.

``/add`` asks the CoC API for the clan before recording it. A tag that does not
exist used to be stored anyway, fail every poll for ever, and still be listed by
``/clans`` as followed.


Modules
-------

``registry.py``, new. Functions over a ``Storage``: ``subscriptions()``,
``subscribe()``, ``unsubscribe()``, ``file_request()``, ``pending_requests()``,
``resolve_request()``. No class; state lives in the database.

``runner.py``, new. Owns the notifier, the registry and the monitors. Holds the
loop that ``WarMonitor.start`` holds today.

``storage.py``: the two new tables, the ``sent`` key change, the migration.

``notifiers.py``: ``send(msg, chat_id, silent=False)``; ``receive`` yields
``Command`` or ``Membership``, handling ``channel_post`` and
``my_chat_member``.

``commands.py``: the operator commands, and dispatch that resolves a chat to
its clans.

``__main__.py``: the new options, and wiring that builds monitors from the
registry instead of from arguments.

``WarMonitor`` keeps ``update`` and the message builders, gains a ``chat_ids``
list used by ``send``, and loses ``start`` and ``answer_commands_until``.


Runtime
-------

The runner holds one ``WarMonitor`` per clan, not per subscription, so two chats
following one clan cost one poll. Each carries the chats subscribed to that
clan.

Each monitor has a next-due time. On start they are spread evenly across
``POLL_INTERVAL`` rather than all falling due together. The loop is:

1. Poll every monitor now due and let it post.
2. Serve commands until the next monitor falls due, exactly as
   ``answer_commands_until`` does today, so a question is answered promptly and
   the poll is not held up behind the chat.
3. Reload the registry if a command changed it, adding or dropping monitors.

A monitor whose clan the CoC API 404s is left in place and retried; a clan tag
can be wrong, and a wrong one should be visible in ``/clans`` rather than
silently dropped.

``WarMonitor.send`` iterates ``chat_ids`` and calls ``send_once`` per chat, so a
chat that is failing does not suppress the others. The existing 429 handling in
the notifier is unchanged and is per request, so it already applies per chat.


Testing
-------

Against the existing suite's style, which drives the monitor with a mocked API
and a recording notifier:

- Two clans in one war each post to their own chats and neither suppresses the
  other. This is ADR 0010's collision and is the test that matters most, since
  the bug it guards is silent.
- Subscribing mid-war backfills, so the new chat receives the next event and
  not the war so far.
- ``/add`` and ``/remove`` from the operator id change what is polled;
  the same from any other id changes nothing.
- ``/request`` writes a row when open and none when closed.
- A command in an unsubscribed chat gets help, not war data.
- ``--archive`` off leaves ``archive`` empty while ``war`` still caches, which
  is ADR 0009's distinction and is easy to regress.
- The ``sent`` migration attributes old rows to the bootstrap chat.


Staging
-------

Each step leaves the current single-clan deployment behaving identically.

1. ``sent`` key and migration, ``send(chat_id)``, the ``channel_post`` fix, and
   the registry with the bootstrap seeding it. Still one clan.
2. The runner, several monitors, and the operator commands behind
   ``--admin-id``.
3. ``--archive`` and ``--open-requests``.

Step 1 defuses the ADR 0010 collision before anything can be added that would
trigger it.
