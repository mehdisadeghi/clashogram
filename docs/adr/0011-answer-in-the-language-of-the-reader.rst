Answer in the language of the reader
====================================

:Status: accepted
:Date: 2026-09-05

Context
-------

Language is chosen per chat and applied by activating one gettext catalogue at
a time, through ``i18n.activate``. The war monitor activates the chat's
language before each send, so posts come out right.

Commands do not. ``answer`` activates the language of the chat that spoke and
then builds every answer the command produced, including the ones addressed
somewhere else. A request filed from a Persian chat therefore reached the
operator in Persian, and an approval reached the asker in the operator's
language. The runner had the same fault the other way round: a maintenance
notice was built in whichever chat the monitor had posted to last.

Decision
--------

Every message is built in the language of the chat it is addressed to, not the
language of the chat that caused it. ``i18n.active`` reports the current
language so it can be put back, and ``_addressed`` builds one answer under
another chat's language.

Wording addressed to an operator is built once per operator, because two
operators need not read the same language.

Consequences
------------

A cross-chat message is a closure, not a string, since the words cannot be
formatted before the destination is known. That cost falls only on the few
commands that answer more than one chat.
