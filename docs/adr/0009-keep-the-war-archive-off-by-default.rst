Keep the war archive off by default
===================================

:Status: accepted
:Date: 2026-08-21

Context
-------

Every war that ends is written whole into the ``archive`` table and kept
forever. Nothing in the running bot ever reads it back. Its only readers are
``clashogram-export`` and ``clashogram-import``, which exist so a warlog can be
carried between deployments.

One clan produces a few finished wars a month and the cost is invisible. Once
the operator can add clans over Telegram it stops being invisible, and it grows
in the one direction that never reverses: a war is written when it ends and is
never removed.

Decision
--------

``--archive`` turns the table on and it is off by default, so an instance keeps
war payloads only when somebody has said they want them. It is read from the
``ARCHIVE`` environment variable, which is how the Kubernetes deployment sets
it.

The flag gates ``archive_war`` and nothing else.

Consequences
------------

An instance that never sets it has nothing to export. That is the point, but it
is a trap for anybody who turns the flag on after a season and finds the wars
before it are gone. Wars are archived from the moment it is set, never
retroactively.

The ``war`` table is explicitly not covered. It looks like the same kind of
retention and is not: it is the finished-league-war cache from
`0005 <0005-cache-finished-league-wars.rst>`_, and it exists to keep the poll
off the CoC API for wars that can no longer change. Disabling it would trade
disk, which is cheap and bounded by a season, for request rate, which is the
actual scarce resource. An earlier sketch of this decision grouped the two
together as "storage" and would have made the instance more expensive to run in
the name of making it lighter.

Deduplication in ``sent`` is likewise untouched. It is not retention: drop it
and every poll resends every message it has already sent.
