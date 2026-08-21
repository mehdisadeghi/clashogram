Key sent messages by chat as well as by war
===========================================

:Status: accepted
:Date: 2026-08-21

Context
-------

``sent`` is keyed on ``(war_id, msg_id)``, and ``war_id`` is built by
``WarInfo.create_war_id`` from the payload's own slot order rather than from the
asking clan's, so that both sides of a war name it identically. That was
deliberate and is right for one clan: it means the same war is one war however
it is reached, whether directly or through a league group.

It stops being right the moment two subscribed clans meet each other. Both
resolve the war to the same id, both walk the same message ids, and the first
one served marks them sent. The second is then told it has already posted
messages it has never posted, and its chat is simply skipped. Nothing errors and
nothing is logged.

The pairing is not far-fetched. Clans of a similar strength are matched
repeatedly, and an operator adds the clans they know.

Decision
--------

``sent`` gains ``chat_id`` and is keyed on ``(war_id, msg_id, chat_id)``.
Delivery is recorded per destination, which is what it always meant.

``create_war_id`` is unchanged. A war keeping one identity across both clans is
still correct, and is what makes the league cache work.

Existing rows are migrated once, taking the bootstrap chat id, because that is
the only chat a warlog written under the old key can have been sent to.

Consequences
------------

A chat added part way through a war has no rows and would be sent the war from
its beginning. Subscribing therefore backfills ``sent`` for the war in progress,
so a new chat starts from the next thing that happens rather than from a
recital of everything that already has.

``sent`` grows with chats as well as wars. It is roughly sixty bytes a row and a
war produces on the order of a hundred, so a clan followed by three chats costs
a few tens of kilobytes a war. Rows for wars long finished are never read again
and are not yet pruned.
