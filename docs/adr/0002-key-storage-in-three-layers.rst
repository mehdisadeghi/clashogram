Key storage in three layers
===========================

:Status: accepted
:Date: 2026-08-09

Context
-------

Three kinds of thing end up in the warlog and they do not share a key. Wars are
facts. Stars and season totals are derived from those facts. Which messages
have been delivered belongs to whoever they were delivered to.

Decision
--------

Facts are keyed by war tag, aggregates by clan tag and season, delivery by
subscription. Clan *tag* rather than name, because tags are permanent. A layer
is only built when something reads it.

Consequences
------------

Aggregates are a pure function of facts, so they are derived once and shared
rather than recomputed per reader.

``sent`` currently has no subscription column, because there is only one
subscription. That is the single schema change multi-tenancy needs: two tenants
watching one clan into different channels would otherwise mark each other's
messages as delivered and the second channel would receive nothing.
