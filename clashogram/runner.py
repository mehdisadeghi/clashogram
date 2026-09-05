########################################################################
# The loop
########################################################################
"""Follows every subscribed clan from one process.

`WarMonitor` owned the loop while there was one of them. One long poll
cannot run once per monitor, so the loop lives here and asks each
monitor in turn."""
import datetime
import logging
import time

import requests

from . import commands, i18n, registry
from .i18n import gettext_ as _

POLL_INTERVAL = 60
IDLE_TICK = 1
BACKOFF = POLL_INTERVAL * 10
logger = logging.getLogger(__name__)


def publish_menu(ctx, notifier):
    """Put the commands in Telegram's own menu, once per language.

    Nothing is posted to any chat. The operator's menu is scoped to
    their chat, so no one else is offered commands they cannot run."""
    try:
        for lang in i18n.LANGUAGES:
            i18n.activate(lang)
            notifier.publish_menu(commands.menu(),
                                  language_code=None if lang == i18n.DEFAULT
                                  else lang.split('_')[0])
        for operator in commands.operator_ids(ctx):
            i18n.activate(ctx.db.chat_lang(operator))
            notifier.publish_menu(commands.menu(for_operator=True),
                                  chat_id=operator)
    except requests.RequestException as err:
        logger.warning('Could not publish the menu (%s).', _describe(err))
    finally:
        i18n.activate(i18n.DEFAULT)


def run(ctx, build_monitor, notifier):
    """Poll every followed clan and answer whoever asks, forever."""
    publish_menu(ctx, notifier)
    due = {}
    while True:
        sync(ctx, build_monitor, due)
        now = time.monotonic()
        for clan_tag, monitor in list(ctx.monitors.items()):
            if due.get(clan_tag, 0) <= now:
                due[clan_tag] = time.monotonic() + poll(
                    ctx, monitor, notifier)
        deadline = min(due.values(), default=time.monotonic() + IDLE_TICK)
        answer_until(ctx, notifier, deadline)


def sync(ctx, build_monitor, due):
    """Bring the monitors in line with the subscriptions.

    New clans are spread across the interval rather than all falling due
    at once, so adding several does not fire them together."""
    wanted = registry.clans_with_chats(ctx.db)
    for clan_tag in list(ctx.monitors):
        if clan_tag not in wanted:
            del ctx.monitors[clan_tag]
            due.pop(clan_tag, None)
    fresh = [tag for tag in wanted if tag not in ctx.monitors]
    for index, clan_tag in enumerate(fresh):
        ctx.monitors[clan_tag] = build_monitor(clan_tag, wanted[clan_tag])
        due[clan_tag] = time.monotonic() + index * POLL_INTERVAL / len(fresh)
    for clan_tag, chats in wanted.items():
        ctx.monitors[clan_tag].chat_ids = chats


def poll(ctx, monitor, notifier):
    """Fetch one clan and report it. Returns seconds until it is due again.

    A failing clan backs itself off and leaves the others alone. One
    private warlog stopped the whole process before, which with several
    clans would silence them all."""
    try:
        leagueinfo = monitor.coc_api.get_currentleague(monitor.clan_tag)
        monitor.leagueinfo = leagueinfo
        if leagueinfo:
            # Already fetched, so not asked for a second time.
            for previous_war in leagueinfo.get_previous_wars():
                monitor.update(previous_war)
            current_war = leagueinfo.get_current_war()
            next_war = leagueinfo.get_next_war()
            if current_war:
                monitor.update(current_war)
            if next_war:
                monitor.update(next_war)
        else:
            monitor.update()
        _recovered(monitor)
        _left_maintenance(ctx, notifier)
        return POLL_INTERVAL
    except requests.HTTPError as err:
        return _back_off(ctx, monitor, notifier, err)
    except requests.RequestException as err:
        # A dropped connection or dns blip is ordinary for a process
        # that polls for months. Dying costs a restart and fixes
        # nothing.
        logger.warning('Cannot reach CoC for %s (%s), retrying.',
                       monitor.clan_tag, type(err).__name__)
        return BACKOFF


def _describe(err):
    response = getattr(err, 'response', None)
    if response is None:
        return type(err).__name__
    return f'{response.status_code} {response.json().get("description", "")}'


_complained = {}


def _tell(ctx, notifier, monitor, build, trouble):
    """Tell the operators, once per spell of trouble.

    This went to every chat of the clan on every retry before: a six
    hour CoC maintenance meant thirty six messages in a channel, about
    something only the operator can act on."""
    if _complained.get(monitor.clan_tag) == trouble:
        return
    _complained[monitor.clan_tag] = trouble
    _say(ctx, notifier, build)


def _entered_maintenance(ctx, notifier, err):
    """Maintenance is the API's, not a clan's, so it is said once for the
    instance and kept across a restart. A long window usually means a
    game update; the API carries no version to compare."""
    if ctx.db.setting('maintenance_since'):
        return
    ctx.db.set_setting('maintenance_since',
                       datetime.datetime.now(datetime.timezone.utc)
                       .isoformat(timespec='seconds'))
    said = ''
    try:
        said = err.response.json().get('message') or ''
    except ValueError:
        pass
    _say(ctx, notifier, lambda: _('CoC went into maintenance.{detail}').format(
        detail=f' {said}' if said else ''))


def _left_maintenance(ctx, notifier):
    since = ctx.db.setting('maintenance_since')
    if not since:
        return
    ctx.db.set_setting('maintenance_since', '')
    began = datetime.datetime.fromisoformat(since)
    minutes = int((datetime.datetime.now(datetime.timezone.utc) - began)
                  .total_seconds() // 60)
    _say(ctx, notifier,
         lambda: _('CoC is back. Maintenance ran {hours}h {minutes}m '
                   'from {began}.').format(
             hours=minutes // 60, minutes=minutes % 60,
             began=began.strftime('%Y-%m-%d %H:%M UTC')))


def _say(ctx, notifier, build):
    """Each operator in their own language, so the wording is built once
    per reader."""
    here = i18n.active()
    for operator in commands.operator_ids(ctx):
        i18n.activate(ctx.db.chat_lang(operator))
        try:
            notifier.reply(operator, build())
        except requests.RequestException as err:
            logger.warning('Could not tell the operator (%s).',
                           _describe(err))
    i18n.activate(here)


def _recovered(monitor):
    _complained.pop(monitor.clan_tag, None)


def _back_off(ctx, monitor, notifier, err):
    status = err.response.status_code
    if status in (500, 502, 504):
        logger.warning('CoC server error %s for %s, retrying.',
                       status, monitor.clan_tag)
        return BACKOFF
    if status == 503:
        logger.warning('CoC maintenance for %s, retrying.', monitor.clan_tag)
        _entered_maintenance(ctx, notifier, err)
        return BACKOFF
    if status == 404:
        logger.warning('CoC does not know %s, retrying.', monitor.clan_tag)
        return BACKOFF
    if status == 403 and not monitor.coc_api.get_claninfo(
            monitor.clan_tag).is_warlog_public:
        _tell(ctx, notifier, monitor,
              lambda: _('Warlog must be public boss! ☠️'), 'warlog')
        return BACKOFF
    _tell(ctx, notifier, monitor,
          lambda: _('☠️ 😵 App is broken boss! Come over and fix me please!'),
          'broken')
    raise err


def _reply(notifier, answer):
    """A chat we cannot post to must not swallow the answers meant for
    the others. An announcement goes to every chat at once."""
    try:
        notifier.reply(answer.chat_id, answer.text, answer.choices)
    except requests.RequestException as err:
        logger.warning('Telegram refused us for %s (%s).',
                       answer.chat_id, _describe(err))


def answer_until(ctx, notifier, deadline):
    """Wait out the poll interval answering whoever asks.

    The chat is served while the war poll sleeps, so a question is not
    left waiting a minute and the poll is not held up behind it."""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        answered = False
        try:
            for event in notifier.receive():
                for answer in commands.handle(ctx, event):
                    _reply(notifier, answer)
                answered = True
        except requests.RequestException as err:
            # The status matters: 409 is something else polling the
            # same bot, 400 is a reply we built with bad html.
            logger.warning('Telegram refused us (%s), retrying.',
                           _describe(err))
        if not answered:
            # A notifier that does not block would spin here.
            time.sleep(min(remaining, IDLE_TICK))
