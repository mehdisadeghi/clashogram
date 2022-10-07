.. contents::
   :depth: 3
..

clashogram |Build Status| |Build status| |Pypi status|
======================================================

Clash of Clans war moniting for telegram channels.

    NOTE: Clash of Clans API data is always 10 minutes behind the game
    events. This is not a bug in this program.

    NOTE: Your warlog must be public.

``clashogram`` monitors your clan's warlog and posts the following
messages to a Telegram channel:

1. Preparation started (with clans and players information)
2. War started
3. New attacks (with details)
4. War over

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

From pypi::

    $ pip install clashogram

From Github (for development)::

    $ git clone https://github.com/mehdisadeghi/clashogram.git
    $ cd clashogram
    $ pip install flit
    $ flit install --symlink

With Docker
-----------

In order to run the latest docker version do the following::

    $ docker run -it mehdisadeghi/clashogram:latest

This will prompt for the necessary parameters and start the app. Slighty better would be::

    $ docker run --env-file=<ENV_FILE> --name clashogram --restart=always -d mehdisadeghi/clashogram:latest

This will run the container in the background and restart it if it fails. ``ENV_FILE`` should contain one ``key=value`` per line (the app params). In my experience this works good enought, however for some reason sometimes docker does not start the container after reboot. In that case a systemd unit or similar could be used to start the ``clashogram`` container above.

Usage
-----

In order to use the program do the following:

1. Open a Clash of Clans developer account at
   https://developer.clashofclans.com/.
2. Find your external IP address using a website like
   `this <https://whatismyipaddress.com/>`__.
3. Go to your CoC developer page and create an API token for the IP number you just found.
4. Create a Telegram bot using BotFather and copy its token.
5. [For Channels] Create a new Telegram channel and add the bot you just created as to that channel. As of May 2020, bots can only be added as administrators to channels. If you want to post to a group instead of a channel see the instructions below.
6. [For Groups] Add the bot you just created to your Telegram group (create one if necessary).

Obtaining The Chat ID
~~~~~~~~~~~~~~~~~~~~~
In order to send messages to a channel or a chat in Telegram we need the ID of that chat, i.e. ``chat_id``. This is how Telegram API works. For public channels it is possible to use the name of the channel prefixed with ``@`` as ``chat_id``, e.g. ``@mypublicchannel``. However, for private channels and group chats we need to obtain the ``chat_id``.

Take the following steps to obtain the correct ``chat_id``:

1. Add the bot to the group or channel
2. Make sure to write something in the channel/chat
3. Use the ``bot_token`` from the step 4 of the previous section and run one of these this command::

    # For a group chat run this
    $ curl --silent --request POST https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates | jq '.result | map(select(.message.chat.type == "group")) | .[0].message.chat.id'

    # For a channel run this
    $ curl --silent --request POST https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates | jq '.result | map(select(.channel_post.chat.type == "channel")) | .[0].channel_post.chat.id'

You can omit the `jq <https://stedolan.github.io/jq/>`__ part and just search for a ``type=group`` or ``type=channel`` in the output and take note of its ``id``. This is what we will use in the rest of this document as ``chat_id`` for channels and groups. Remember that you can also use ``@yourpublicchannel`` form as ``chat_id`` for public channels.

Now to make sure if the ``chat_id`` realy points to a chat, run the following command and see whether your bot can post to your channel or group chat::

    $ curl --request POST --url https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage\?chat_id\=<CHAT_ID_FROM_THE_PREVIOUS_STEP>\&text\=hi

If it does not work, make sure you have done the previous steps correctly or open an issue on GitHub.

Starting The Program
~~~~~~~~~~~~~~~~~~~~

Now we can proceed with starting the program. Run the following command to install and start the program::

    $ pip install clashogram
    $ clashogram --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --chat-id <CHAT_ID> --forever

    NOTE: Remember that channel names begin with ``@`` and chat_ids are numbers (often negative).


If you don't want attack updates in your channel add ``--mute-attacks`` to the above command.

In order to have messages in a different locale do the following and
then run the program::

    $ export LANGUAGE=<LANGUAGE_CODE>
    # This is for Persian
    $ export LANGUAGE=fa

Or do it in one step::

    $ LANGUAGE=fa clashogram --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --chat-id <CHAT_ID>

Setting Language on Windows
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Make sure to run ``set LANGUAGE=<your_lang_code_here>`` on windows before running the program.

Run as a service
~~~~~~~~~~~~~~~~

The simplest way to use Clashogram is leave it running in background
using either `byobu <byobu.org>`__ or `GNU
Screen <https://www.gnu.org/software/screen/>`__. Another solution is to
install a systemd unit::

    [Unit]
    Description=Clashogram Daemon
    After=network.target

    [Service]
    WorkingDirectory=/path/to/clashogram/
    EnvironmentFile=/path/to/env/file
    ExecStart=/path/to/python /path/to/clashogram
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
beforehand::

    python -m unittest discover

Or with ``py.test``::

    pip install pytest
    py.test tests.py

I18N
----

In order toadd or update a new language catalog do the following::

    pip install babel # Install the babel i18n tool first.

::

    pybabel init -i clashogram/locales/messages.pot -d clashogram/locales -l <LANGUAGE_CODE>
    pybabel update -i clashogram/locales/messages.pot -d clashogram/locales -l <LANGUAGE_CODE>

For example::

    pybabel init -i clashogram/locales/messages.pot -d clashogram/locales -l fa
    pybabel update -i clashogram/locales/messages.pot -d clashogram/locales -l fa

In case of adding new messages extract them and compile again::

    pybabel extract clashogram/ -o clashogram/locales/messages.pot --project Clashogram --version 0.6.0
    pybabel update -i clashogram/locales/messages.pot -d clashogram/locales
    pybabel compile -d clashogram/locales

For more information on internationalization see
`Babel <http://babel.pocoo.org/en/latest/setup.html>`__.

Credits
-------
Thanks Ali Ayatollahi and other members from IRAN clan (tag #YVL0C8UY) for the initial idea and testing.


License
-------

MIT

.. |Build Status| image:: https://travis-ci.org/mehdisadeghi/clashogram.svg?branch=master
   :target: https://travis-ci.org/mehdisadeghi/clashogram
.. |Build status| image:: https://ci.appveyor.com/api/projects/status/ovixrhmsp3og4nt4/branch/master?svg=true
   :target: https://ci.appveyor.com/project/mehdisadeghi/clashogram/branch/master
.. |Pypi status| image:: https://img.shields.io/pypi/v/clashogram.svg
   :target: https://pypi.python.org/pypi/clashogram


Russian Translations
--------------------
You can read this document in Russian thanks to Timur from Illuminati clan. Thanks Timur!
`this document in Russian <README_RU.rst>`__


راهنمای فارسی
-------------
برای مطالعه راهنمای فارسی به `این آدرس <http://mehdix.ir/clashogram.html>`__ سر بزنید.
