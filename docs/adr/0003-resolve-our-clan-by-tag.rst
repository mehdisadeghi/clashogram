Resolve our clan by tag, not by payload slot
============================================

:Status: accepted
:Date: 2026-08-09

Context
-------

``/clanwarleagues/wars/{warTag}`` names its two sides ``clan`` and ``opponent``
arbitrarily. Our clan sits in ``opponent`` in roughly half of the league
rounds. Everything here read ``data['clan']`` as us, so those rounds were
dropped by the filter that picks our wars, and reading one anyway would have
announced a loss as a win.

Decision
--------

``WarInfo`` takes the tag of the clan we asked about and resolves which slot it
occupies once. The ``clan_`` and ``op_`` properties read through that.
``create_war_id`` deliberately keeps reading the payload's own slot order.

Consequences
------------

Omitting the tag preserves the old behaviour, so the regular war path is
untouched.

War ids stay stable no matter which clan is asking. Keying them on our own side
would give one war two ids, splitting the delivery flags and reposting the
whole war.
