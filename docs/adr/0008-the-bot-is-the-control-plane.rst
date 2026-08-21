Let the bot operate the instance
================================

:Status: accepted
:Date: 2026-08-21

Context
-------

One clan tag and one chat id arrive as startup options and never change. A
second clan means a second deployment, with its own secret, its own volume and
its own copy of the CoC token. That is the whole cost of saying yes to somebody
who asks, and it is why the answer has always been no.

The instance is not meant to become a free service for every player. What is
wanted is narrower: the operator adds a clan when they choose to, and somebody
who wants in can ask rather than be told to run their own.

Decision
--------

Subscriptions move into the warlog as ``(clan_tag, chat_id)`` rows, and the
bot itself is how they are managed. A privileged user id, given as
``--admin-id``, may list, add and remove them from any chat. Nobody else can
change anything.

That one id is the owner, not the only operator. The owner may name others over
Telegram, and they may then follow clans and settle requests, which is the
work that does not scale to one person. Only the owner names them, so a
co-operator can neither unseat the owner nor recruit further, and the owner
cannot be removed at all, including by themselves. Somebody learns the user id
to be named by sending ``/chatid`` to the bot in a direct chat, where the chat
id is their own id.

Anyone may send ``/request <clan tag>`` in the chat they want served. It files
a row and tells the operator. It grants nothing. Requests are refused outright
unless ``--open-requests`` is given, which it is not by default, so an instance
that never wants to hear from strangers never does.

Startup options are kept as a bootstrap: ``--clan-tag`` with ``--chat-id``
ensures that one pair exists and is otherwise idle. The existing deployment
therefore behaves exactly as it does today.

Polling is grouped by clan rather than by subscription, so two chats following
the same clan cost one poll rather than two. The command loop moves out of
``WarMonitor`` and into a runner that owns the notifier and serves every clan,
because a single long poll cannot be run once per monitor.

Consequences
------------

The scarce resource is the CoC API, not the server. A clan costs roughly two
requests a minute at rest and more during a league season, so how many clans an
instance can hold is a throttling question that this decision does not answer.
Polls are staggered across the interval rather than fired together, which
spreads the load but does not raise the ceiling.

``WarMonitor`` loses ``start`` and ``answer_commands_until``. It polls one clan
and reports; it no longer owns the process.

Telegram decides where the operator can be recognised, not this design. A post
in a channel carries no author at all, so operator commands cannot work inside
one and a channel is driven from a direct message instead. The bot announces
itself when it is added somewhere, and answers ``/chatid`` to anyone, so the id
that direct message needs does not have to be hunted for. A group carries its
author and needs none of that: the operator adds the bot and says ``/add`` on
the spot.

Two things are deliberately left undone. Every message is still rendered in the
one locale the process was started with, so a second clan speaking another
language is served Persian; this instance is ``fa_IR`` and that is understood.
And a chat following more than one clan gets each answer prefixed with the clan
name rather than being asked which it meant, which is enough while the number
of clans is small and will not be when it is not.
