The bot answers, it does not remind
===================================

:Status: accepted
:Date: 2026-08-09

Context
-------

Every message this bot sends reports something that happened: a war started,
somebody attacked, a war ended. A reminder reports that something has *not*
happened, on a timer, which is nagging rather than reporting.

Decision
--------

No unsolicited reminders. Anything of that shape is a command somebody chooses
to send. ``/missing`` answers who still has attacks left, when asked.

Consequences
------------

The standings posted when a round ends are a deliberate exception: a round
ending is an event and the war over message already announces it unprompted.
That exception was decided explicitly, not by default.

Anything push shaped needs the same explicit decision before it is added.
