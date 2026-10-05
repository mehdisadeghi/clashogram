A failed send belongs to the chat, not the clan
===============================================

:Status: accepted
:Date: 2026-10-05

Context
-------

``poll`` covers a clan's whole turn: fetching the war from CoC and posting it
to the chats that follow it. It catches ``HTTPError`` and reads the status code
as CoC's, which it was written for, and ends the process on a code it does not
recognise.

Posting happens inside that turn, so Telegram's status codes were read as CoC's
too. One user had blocked the bot, so every send to them returned 403.
``_back_off`` checked whether the clan's warlog was public, found that it was,
told the operator the app was broken and re-raised. The container died, came
back, polled the same clan and died again: 844 restarts over three days, each
one an alarm about a clan that was fine.

Decision
--------

Handle a send failure in ``send_once``, where the chat is known, so it never
reaches ``poll``. What reaches ``_back_off`` is CoC's alone.

403 means blocked, kicked, deleted or deactivated, none of which recover until
the bot is added back, and being added back announces itself. So the chat is
dropped, along with every clan followed in it. Other statuses still propagate:
a 400 is usually a message we built wrong and should be loud.

Consequences
------------

One chat can no longer stop every clan, and no clan is polled for a chat that
will never see it.

The operator is not told that a chat has dropped out, as in
:doc:`0012-the-operator-is-told-what-they-can-act-on`. It is a line in the log,
and the chat is gone from ``/activity``.

A transient 403 would cost that chat its subscriptions and need adding back.
