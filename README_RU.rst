.. contents::
   :depth: 3
..

clashogram |Build Status| |Build status| |Pypi status|
======================================================

Отслеживание войн и их деталей для Clash of Clans.

    Примечание: данные Clash of Clans API всегда обновляются в течении 10 минут. Это не баг в программе.
    
``clashogram`` отслеживает ход войны вашего клана и через Telegram-канал оповещает вас о следующем:
    
    1. Стадия подготовки (вместе с информацией о кланах и их участиях)
    2. Начало войны
    3. Новые атаки (с деталями)
    4. Конец войны

Требования
----------

Для запуска программы вам необходимо иметь установленную версию python 3.3 и выше. Вам также нужен ``pip`` для установки зависимостей python. Более того, использование `virtualenv <https://virtualenv.pypa.io/en/stable/>`__ упрощает установку, в противном случае вы должны установить всё общесистемно. На ОС Linus вы должны будете запускать программу через команду ``sudo``, на OS Windows от имени администратора.


Установка
---------

Из pypi:

::

    pip install clashogram

Из Github:

::

    git clone https://github.com/mehdisadeghi/clashogram.git
    cd clashogram
    install -r requirements.txt
    python setup.py install


Использование
-------------

Для начала использвания вам требуется следующее:

1. Открыть учетную запись разработчика Clash of Clans на https://developer.clashofclans.com/.
2. Узнать ваш внешний IP адрес на сайти типа `этого <https://whatismyipaddress.com/>`__.
3. Перейти на вашу учетную запись разработчика CoC и создать токен включая ваш IP.
4. Создать бота Telegram через @BotFather и скопировать токен бота.
5. Создать новую группу или канал в Telegram и добавить туда бота, который вы создали, и дать ему права администратора.
    
Теперь можно запускать программу:

::

    pip install clashogram
    clashogram --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --channel-name <TELEGRAM_CHANNEL_NAME> --forever

В случае, если вам требуется изменить язык сообщений, используйте команды:

::

    export LANGUAGE=<LANGUAGE_CODE>
    К примеру,
    export LANGUAGE=ru

Или сделайте это одной командой:

::

    LANGUAGE=ru clashogram --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --channel-name <TELEGRAM_CHANNEL_NAME>

Проблемы при использовании Windows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Если вы решите запустить Clashogram на Windows, обязательно введите ``set LANGUAGE=<lang_code>`` в вашем терминале, чтобы избежать ошибок в кодировке.

Запуск приложения в виде службы
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Самый простой способ использования Clashogram - оставить его в фоновом режиме, используя либо `byobu <byobu.org>`__, либо `GNU
Screen <https://www.gnu.org/software/screen/>`__. Другое решение - установить системный блок:

::

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

    Для более конкретной информации по вашей ОС воспользуйтесь поиском в интернете.



Вклад (Pull Request'ы приветствуются!)
--------------------------------------

Уведомления Telegram изолированы от остальной части программы. Вы можете заменить его на что-нибудь свое, чтобы ваши сообщения отправлялись куда-то еще.

Форкайте и клонируйте репозиторий и отправляйте мне Pull Request'ы. Убедитесь, что в тестах заранее:

::

    python -m unittest discover

Или через ``py.test``:

::

    pip install pytest
    py.test tests.py


Интернационализация
-------------------

Чтобы добавить или обновить новый каталог языков, выполните следующее:

::

    pip install babel # Установите сначала инструмент.

::

    python setup.py init_catalog -l <LANGUAGE_CODE>
    python setup.py update_catalog -l <LANGUAGE_CODE>

К примеру:

::

    python setup.py init_catalog -l ru
    python setup.py update_catalog -l ru

В случае добавления новых сообщений извлеките их и скомпилируйте снова:

::

    python setup.py extract_messages
    python setup.py compile_catalog


Для получения дополнительной информации о интернационализации см. `Babel <http://babel.pocoo.org/en/latest/setup.html>`__.

Участие
-------

Спасибо Ali Ayatollahi и других участников из клана Iran (тэг #YVL0C8UY) за предоставленную идею и тестирование.
Спасибо Timur и других участников из клана Illuminati за перевода этого документа на русский.

Лицензия
--------

MIT
