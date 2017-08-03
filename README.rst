.. contents::
   :depth: 3
..

clashogram |Build Status| |Build status|
========================================

Clash of Clans war moniting for telegram channels.

    NOTE: Clash of Clans API data is always 10 minutes behind the game
    events. This is not a bug in this program.

``clashogram`` monitors your clan's warlog and posts the following
messages to a Telegram channel: 1. Preparation started (with clans and
players information) 2. War started 3. New attacks (with details) 4. War
over

Requirements
------------

To run the program you need to have python 3.3 or higher. You will also
need ``pip`` to install python dependencies. Moreover, using a
`virtualenv <https://virtualenv.pypa.io/en/stable/>`__ makes
installation much easier, otherwise you have to install everything
system-wide. On Linux you would need to run commands with ``sudo``, on
windows with administrator account.

Installation
------------

From pypi:

::

    pip install clashogram

From Github:

::

    git clone https://github.com/mehdisadeghi/clashogram.git
    cd clashogram
    install -r requirements.txt
    python setup.py install

Usage
-----

In order to use the program do the following:

1. Open a Clash of Clans developer account at
   https://developer.clashofclans.com/.
2. Find your external IP address using a website like
   `this <https://whatismyipaddress.com/>`__.
3. Go to your CoC developer page and create an API token for the IP
   number you just found.
4. Create a Telegram bot using BotFather and copy its token.
5. Create a new Telegram group and add the bot you just created as an
   administrator to that group.

Now you can run the following command:

::

    pip install clashogram
    clashogram.py --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --channel-name <TELEGRAM_CHANNEL_NAME>

In order to have messages in a different locale do the following and
then run the program:

::

    export LANGUAGE=<LANGUAGE_CODE>
    e.g.
    export LANGUAGE=fa

Or do it in one step:

::

    LANGUAGE=fa clashogram.py --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --channel-name <TELEGRAM_CHANNEL_NAME>

Run as a service
~~~~~~~~~~~~~~~~

The simplest way to use Clashogram is leave it running in background
using either `byobu <byobu.org>`__ or `GNU
Screen <https://www.gnu.org/software/screen/>`__. Another solution is to
install a systemd unit:

::

    [Unit]
    Description=Clashogram Daemon
    After=network.target

    [Service]
    WorkingDirectory=/path/to/clashogram/
    EnvironmentFile=/path/to/env/file
    ExecStart=/path/to/python /path/to/clashogram.py
    Restart=on-failure
    User=someuser

    [Install]
    WantedBy=multi-user.target

Search internet for more information on installing systemd units on your
OS.

Contribution (PRs welcome!)
---------------------------

The Telegram notification is isolated from the rest of the program. You
can replace it with anything else to have your messages sent to
somewhere else.

Fork and clone the repository and send a PR. Make sure tests pass
beforehand:

::

    python -m unittest discover

Or with ``py.test``:

::

    pip install pytest
    py.test tests.py

I18N
----

In order toadd or update a new language catalog do the following:

::

    python setup.py init_catalog -l <LANGUAGE_CODE>
    python setup.py update_catalog -l <LANGUAGE_CODE>

For example:

::

    python setup.py init_catalog -l fa
    python setup.py update_catalog -l fa

In case of adding new messages extract them and compile again:

::

    python setup.py extract_messages
    python setup.py compile_catalog

For more information on internationalization look at
`Babel <http://babel.pocoo.org/en/latest/setup.html>`__.

Have fun!

License
-------

MIT

.. |Build Status| image:: https://travis-ci.org/mehdisadeghi/clashogram.svg?branch=master
   :target: https://travis-ci.org/mehdisadeghi/clashogram
.. |Build status| image:: https://ci.appveyor.com/api/projects/status/ovixrhmsp3og4nt4/branch/master?svg=true
   :target: https://ci.appveyor.com/project/mehdisadeghi/clashogram/branch/master
