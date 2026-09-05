########################################################################
# Languages
########################################################################
"""One translation at a time, chosen per chat.

Every module binds `_` once at import, so `_` here is a function that
reads whichever translation is active, and `activate` is what moves
it."""
import gettext
import os

DOMAIN = 'messages'
LOCALEDIR = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                         'locales')
DEFAULT = 'en'
# Messages are written in english, so it needs no catalogue.
LANGUAGES = {'en': 'English', 'fa_IR': 'فارسی', 'ru': 'Русский'}

_loaded = {}
_current = gettext.NullTranslations()
_active = DEFAULT


def translation(lang):
    if lang not in _loaded:
        _loaded[lang] = gettext.translation(DOMAIN, LOCALEDIR,
                                            languages=[lang], fallback=True)
    return _loaded[lang]


def activate(lang):
    global _active, _current
    _active = lang if lang in LANGUAGES else DEFAULT
    _current = translation(_active)


def active():
    """The language in force, for putting back after answering another
    chat."""
    return _active


def gettext_(message):
    return _current.gettext(message)


def ngettext_(singular, plural, count):
    """One or many. Russian has three forms, so a number in front of an
    english plural is not enough."""
    return _current.ngettext(singular, plural, count)


def noop(message):
    """Mark a string for translation without translating it yet.

    A menu entry is written once and rendered per language, so the
    catalogue needs it before it is used."""
    return message
