Upgrading the warlog to sqlite
==============================

The warlog used to be a ``shelve``. It is a sqlite database now, so an
existing one has to be imported once. Skipping this leaves the bot with
no record of what it already posted and it announces the current war
from the beginning.

Under docker
------------

With the data volume mounted at ``/data``::

    $ docker stop clashogram
    $ cp -a /path/to/volume /path/to/volume.bak

    $ docker run --rm -v /path/to/volume:/data \
        --entrypoint clashogram-import mehdisadeghi/clashogram:latest \
        /data/warlog.db /data/warlog-new.db

    $ cd /path/to/volume
    $ mv warlog.db warlog.db.old && mv warlog-new.db warlog.db

    $ docker rm clashogram
    $ make deploy

The import prints how many messages it carried over. If that number is
zero or smaller than expected, stop and check the file rather than
starting the bot.

Storage backends
----------------

``shelve`` picks its backend when the file is written and the choice
does not travel between machines or python builds, so run the import
where the file was written. To see which backend a file needs, ask the
python that wrote it::

    $ docker exec clashogram python3 -c \
        "import dbm; print(dbm.whichdb('/data/warlog.db'))"

Note ``python3``: on python 2 ``dbm`` is the bare ndbm binding and has
no ``whichdb``. Without a python to hand, ``file warlog.db`` names the
format too.

``dbm.gnu``, ``dbm.ndbm`` and ``dbm.dumb`` all import fine from the
current image. If a file needs a backend the image lacks, run the import
in the image that wrote it and point ``--warlog`` at the result.
