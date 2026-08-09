Store the warlog in sqlite
==========================

:Status: accepted
:Date: 2026-08-09

Context
-------

The warlog was a ``shelve``: pickles in a dbm file. There is no schema, values
execute on load, ``writeback`` holds the whole database in memory, and the dbm
backend is chosen when the file is written and does not travel between machines
or python builds. The live warlog turned out to be ``dbm.gnu``.

Every lookup is also a full scan, and the league standings and the per player
season stats aggregate repeatedly.

Decision
--------

Use ``sqlite3`` from the standard library. One file, in the same data volume,
no new dependency. Import an older shelve once with ``clashogram-import``
rather than reading both formats forever.

Consequences
------------

An existing deployment has to run the import before the first start, otherwise
the bot has no record of what it posted and announces the current war again.
``python:3.13-alpine`` was checked and does have ``_gdbm``, so the container
reads its own old file.

The importer is one way. Nothing writes a shelve again.
