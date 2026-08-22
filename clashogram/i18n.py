########################################################################
# Languages
########################################################################
"""One translation at a time, chosen per chat.

gettext is ambient by nature: every module binds `_` once when it is
imported. So `_` here is a function that reads whichever translation is
active, and `activate` is the only thing that moves it."""
import gettext
import os

DOMAIN = 'messages'
LOCALEDIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'locales')
DEFAULT = 'en'
# English is the language the messages are written in, so it needs no
# catalogue and cannot be missing one.
LANGUAGES = {'en': 'English', 'fa_IR': 'فارسی', 'ru': 'Русский'}

_loaded = {}
_current = gettext.NullTranslations()


def translation(lang):
    if lang not in _loaded:
        _loaded[lang] = gettext.translation(DOMAIN, LOCALEDIR,
                                            languages=[lang], fallback=True)
    return _loaded[lang]


def activate(lang):
    global _current
    _current = translation(lang if lang in LANGUAGES else DEFAULT)


def gettext_(message):
    return _current.gettext(message)
