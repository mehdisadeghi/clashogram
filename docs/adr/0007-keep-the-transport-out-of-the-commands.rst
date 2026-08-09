Keep the transport out of the command layer
===========================================

:Status: accepted
:Date: 2026-08-09

Context
-------

The readme has advertised for years that the Telegram notifier is isolated and
replaceable. Adding commands could easily have hardcoded Telegram into the
command handling and quietly broken that.

Decision
--------

``CommandBot.answer`` takes text and returns text and holds no transport. The
transport lives in ``notifiers.py``, which now carries both halves: ``send`` to
broadcast, ``receive`` and ``reply`` to be asked.

Consequences
------------

A notifier for another chat service supplies three methods and the commands
carry over untouched.

Two things are still not portable. Seven message builders wrap their output in
``<pre>`` and the notifier posts with ``parse_mode=HTML``; that should be
neutralised before a second service is written, not after. And Telegram hands
messages over with a plain long poll, which is why this works with no inbound
port, whereas Discord needs a gateway websocket or a public endpoint for slash
commands. Discord broadcast through a webhook needs neither; Discord commands
do.
