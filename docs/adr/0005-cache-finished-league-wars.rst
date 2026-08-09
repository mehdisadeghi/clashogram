Cache finished league wars and follow the whole group
=====================================================

:Status: accepted
:Date: 2026-08-09

Context
-------

A league group is eight clans over seven rounds, so twenty eight war tags, and
all of them were fetched every sixty second poll for the whole season.

Decision
--------

A finished war cannot change, so keep it and never ask again. Wars still being
played are all still followed, including other clans', because the standings
need every clan in the group.

Consequences
------------

Cost is proportional to the wars actually in progress rather than to the size
of the group. Finished rounds cost nothing.

An earlier version skipped other clans' wars outright once it knew they were
not ours. That was wrong: a war first seen while it was still being played was
never looked at again, so its result never arrived and the standings would have
been built on holes.

The warlog grows monotonically, roughly twenty eight rows a season, and is not
pruned.
