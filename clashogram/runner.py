########################################################################
# The loop
########################################################################
"""Follows every subscribed clan from one process.

`WarMonitor` used to own the loop, which worked while there was one of
them. A single long poll cannot be run once per monitor, so the loop
lives here instead and the monitors are asked in turn."""
import gettext
import logging
import time

import requests

from . import commands, registry

POLL_INTERVAL = 60
IDLE_TICK = 1
BACKOFF = POLL_INTERVAL * 10
_ = gettext.gettext
logger = logging.getLogger(__name__)


def run(ctx, build_monitor, notifier):
    """Poll every followed clan and answer whoever asks, forever."""
    due = {}
    while True:
        sync(ctx, build_monitor, due)
        now = time.monotonic()
        for clan_tag, monitor in list(ctx.monitors.items()):
            if due.get(clan_tag, 0) <= now:
                due[clan_tag] = time.monotonic() + poll(monitor, notifier)
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


def poll(monitor, notifier):
    """Fetch one clan and report it. Returns seconds until it is due again.

    A clan that is failing backs itself off and leaves the others alone.
    One private warlog used to stop the process; with several clans
    followed that would let any one of them silence the rest."""
    try:
        leagueinfo = monitor.coc_api.get_currentleague(monitor.clan_tag)
        monitor.leagueinfo = leagueinfo
        if leagueinfo:
            # These are already fetched, so they are not asked for a
            # second time.
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
        return POLL_INTERVAL
    except requests.HTTPError as err:
        return _back_off(monitor, err)
    except requests.RequestException as err:
        # A dropped connection or a dns blip is ordinary for a process
        # that polls for months, and the network is usually back by the
        # next tick. Dying instead costs a restart and fixes nothing.
        logger.warning('Cannot reach CoC for %s (%s), retrying.',
                       monitor.clan_tag, type(err).__name__)
        return BACKOFF


def _describe(err):
    response = getattr(err, 'response', None)
    if response is None:
        return type(err).__name__
    return f'{response.status_code} {response.json().get("description", "")}'


def _tell(monitor, message, silent=False):
    """Best effort. The network being unreachable is often the very
    reason there is something to say."""
    try:
        monitor.send(message, silent=silent)
    except requests.RequestException:
        logger.warning('Could not reach the chats of %s.', monitor.clan_tag)


def _back_off(monitor, err):
    status = err.response.status_code
    if status in (500, 502, 504):
        logger.warning('CoC server error %s for %s, retrying.',
                       status, monitor.clan_tag)
        return BACKOFF
    if status == 503:
        logger.warning('CoC maintenance for %s, retrying.', monitor.clan_tag)
        _tell(monitor, _('CoC maintenance error, retrying in {seconds} '
                         'seconds.').format(seconds=BACKOFF), silent=True)
        return BACKOFF
    if status == 404:
        logger.warning('CoC does not know %s, retrying.', monitor.clan_tag)
        return BACKOFF
    if status == 403 and not monitor.coc_api.get_claninfo(
            monitor.clan_tag).is_warlog_public:
        _tell(monitor, _('Warlog must be public boss! ☠️'))
        return BACKOFF
    _tell(monitor, _('☠️ 😵 App is broken boss! Come over and fix me please!'))
    raise err


def answer_until(ctx, notifier, deadline):
    """Wait out the poll interval answering whoever asks.

    The chat is served while the war poll sleeps, so a question does not
    wait a minute for an answer and the poll does not wait behind the
    chat."""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        answered = False
        try:
            for event in notifier.receive():
                for target, message in commands.handle(ctx, event):
                    notifier.reply(target, message)
                answered = True
        except requests.RequestException as err:
            # The status and reason matter: a 409 means something else is
            # polling the same bot, a 400 means a reply we built is not
            # valid html, and those want opposite fixes.
            logger.warning('Telegram refused us (%s), retrying.',
                           _describe(err))
        if not answered:
            # A notifier that does not block waiting for messages would
            # spin here otherwise.
            time.sleep(min(remaining, IDLE_TICK))
