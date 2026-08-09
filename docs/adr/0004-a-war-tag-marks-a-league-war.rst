A war tag marks a league war
============================

:Status: accepted
:Date: 2026-08-09

Context
-------

A league war gives each member one attack, a regular war two, and the totals
printed in every message depend on which. ``attacksPerMember`` is not reliably
present in league payloads and can claim two.

Decision
--------

If the war was fetched by war tag it is a league war and the answer is one.
Otherwise read ``attacksPerMember``, falling back to two.

Consequences
------------

The endpoint we used is the source of truth rather than a field we cannot
trust. Fixtures that predate the field still report two, which is correct for
them.
