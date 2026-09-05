The operator is told what they can act on
=========================================

:Status: accepted
:Date: 2026-09-05

Context
-------

The operator's chat was the only place the instance could speak, so everything
went there: being added to a chat, being removed from one, and every clan
dropped with it. None of it asked anything of the operator. It was a log of
what other people were doing with their own chats.

The one thing the log was needed for was the id of a channel. A channel post
carries no author, so no one is recognised inside one and the number had to
arrive somewhere a person could be.

Decision
--------

The bot greets the chat it has just been put in, and tells the operator
nothing. The greeting carries the chat's own id, which is what a channel needs,
delivered where whoever added it is already standing.

What the operator would have read in a log they ask for instead. ``/activity``
gives the numbers and lists chats quietest first, which is where a clan polled
for no one shows up. Trouble and maintenance still arrive unasked, as the two
things only an operator can act on.

``/announce`` is the way back: one message to every chat that follows a clan,
shown back with a button first because there is no unsending it. It goes out in
the operator's own words and language, untranslated, since rendering their
sentence into three languages would put words in their mouth.

Consequences
------------

Nothing tells the operator that a chat has gone quiet or that the bot was
added somewhere. They find out by asking. The trade is a readable mailbox for
news that arrives late.

The bot now speaks to chats directly in two places, the greeting and an
announcement, and either can reach someone who did not ask to hear from it.
The greeting follows from being added. An announcement is rare, and the
operator's judgement.
