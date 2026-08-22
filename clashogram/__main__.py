#!/usr/bin/env python
"""clashogram - Clash of Clans war moniting for telegram channels."""
import json
import logging

import click

from . import commands, i18n, registry, runner
from .api import CoCAPI
from .formatters import MessageFactory, create_standings_msg
from .models import LeagueStandings, WarStats
from .notifiers import DummyNotifier, TelegramNotifier
from .storage import Storage
from .storage import import_shelve as import_shelve_warlog

logger = logging.getLogger(__name__)


@click.command()
@click.option('--coc-token',
              help='CoC API token. Reads COC_API_TOKEN env var.',
              envvar='COC_API_TOKEN',
              prompt=True)
@click.option('--clan-tag',
              help='Tag of clan with hash. With --chat-id, followed at'
                   ' startup. Reads COC_CLAN_TAG env var.',
              envvar='COC_CLAN_TAG')
@click.option('--bot-token',
              help='Telegram bot token. The bot must be admin on the channel.'
                   ' Reads TELEGRAM_BOT_TOKEN env var.',
              envvar='TELEGRAM_BOT_TOKEN',
              prompt=True)
@click.option('--chat-id',
              help=('Numeric ID of a chat or name of a public channel with @.'
                    ' Reads TELEGRAM_CHAT_ID env var.'),
              envvar='TELEGRAM_CHAT_ID')
@click.option('--admin-id',
              help='Numeric Telegram user id allowed to run the operator'
                   ' commands. Reads TELEGRAM_ADMIN_ID env var.',
              envvar='TELEGRAM_ADMIN_ID')
@click.option('--archive/--no-archive',
              default=False,
              help='Keep finished wars so they can be exported.'
                   ' Reads ARCHIVE env var.',
              envvar='ARCHIVE')
@click.option('--open-requests/--no-open-requests',
              default=False,
              help='Let anyone ask for a clan to be followed.'
                   ' Reads OPEN_REQUESTS env var.',
              envvar='OPEN_REQUESTS')
@click.option('--mute-attacks',
              is_flag=True,
              help='Do not send attack updates.')
@click.option('--warlog',
              help='Warlog file path.',
              envvar='WARLOG',
              default='warlog.db',
              type=click.Path())
@click.option('--loglevel',
              default='WARNING',
              type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR',
                                 'CRITICAL']),
              help="Set the logging level")
@click.option('--dryrun',
              is_flag=True,
              help='Do not save and send anything.')
def main(coc_token, clan_tag, bot_token, chat_id, admin_id, archive,
         open_requests, mute_attacks, warlog, loglevel, dryrun):
    """Publish war updates to telegram chats."""
    if loglevel:
        logging.basicConfig(level=loglevel)
    # Every chat picks its own; this is only what an unset chat gets.
    i18n.activate(i18n.DEFAULT)

    if bool(clan_tag) != bool(chat_id):
        raise click.UsageError(
            '--clan-tag and --chat-id are followed as a pair; give both or'
            ' neither and manage clans over Telegram instead.')

    notifier = TelegramNotifier(bot_token)

    if dryrun:
        warlog = 'dryrun.db'
        notifier = DummyNotifier()

    with Storage(warlog, bootstrap_chat_id=chat_id) as db:
        coc_api = CoCAPI(coc_token, cache=db)
        if clan_tag:
            registry.subscribe(db, clan_tag, chat_id)

        def build_monitor(tag, chat_ids):
            monitor = WarMonitor(db, coc_api, tag, notifier, chat_ids,
                                 archive=archive)
            monitor.mute_attacks = mute_attacks
            return monitor

        ctx = commands.Context(db=db, monitors={}, admin_id=admin_id,
                               open_requests=open_requests, coc_api=coc_api)
        runner.run(ctx, build_monitor, notifier)


@click.command()
@click.argument('warlog_path', type=click.Path(exists=True))
@click.argument('archive_path', type=click.Path())
def export_wars(warlog_path, archive_path):
    """Write the archived wars out as one json object per line."""
    written = 0
    with Storage(warlog_path) as db, \
            open(archive_path, 'w', encoding='utf-8') as out:
        for war_id, payload in db.archived_wars():
            out.write(json.dumps({'war_id': war_id, 'war': payload},
                                 ensure_ascii=False) + '\n')
            written += 1
    click.echo(f'Exported {written} wars.')


@click.command()
@click.argument('archive_path', type=click.Path(exists=True))
@click.argument('warlog_path', type=click.Path())
def import_wars(archive_path, warlog_path):
    """Read back an archive written by clashogram-export."""
    read = 0
    with Storage(warlog_path) as db, \
            open(archive_path, encoding='utf-8') as archive:
        for line in archive:
            record = json.loads(line)
            db.archive_war(record['war_id'], record['war'])
            read += 1
    click.echo(f'Imported {read} wars.')


@click.command()
@click.argument('shelve_path', type=click.Path(exists=True))
@click.argument('warlog_path', type=click.Path())
@click.argument('chat_id')
def import_warlog(shelve_path, warlog_path, chat_id):
    """Import a pre-sqlite shelve warlog into a sqlite one.

    The chat the old warlog was sent to has to be named, because delivery
    is now recorded per chat and the shelve did not record one."""
    with Storage(warlog_path) as db:
        click.echo(
            f'Imported {import_shelve_warlog(shelve_path, db, chat_id)}'
            ' messages.')


def serverless(db, coc_token, clan_tag, bot_token, chat_id):
    """Publish war updates to a telegram channel."""
    coc_api = CoCAPI(coc_token)
    notifier = TelegramNotifier(bot_token)
    monitor = WarMonitor(db, coc_api, clan_tag, notifier, [chat_id])
    monitor.update()


########################################################################
# Main war monitor class
########################################################################

class WarMonitor:
    def __init__(self, db, api, tag, notifier, chat_ids=(), archive=False):
        """Scan warlog for war updates.

        Calling `update` will fetch one update, notify the changes and
        return. The loop that calls it lives in `runner`.

        Arguments:
            db -- A persistant dictionary-like object.
            api -- Api object
            tag -- Clantag
            notifier -- Notifier object
            chat_ids -- Chats this clan is reported to
            archive -- Whether finished wars are kept
        """
        self.db = db
        self.clan_tag = tag
        self.coc_api = api
        self.notifier = notifier
        self.chat_ids = list(chat_ids)
        self.archive = archive
        self.warinfo = None
        self.msg_factory = None
        self.warstats = None
        self.leagueinfo = None
        self._mute_attacks = False

    @property
    def mute_attacks(self):
        return self._mute_attacks

    @mute_attacks.setter
    def mute_attacks(self, value):
        self._mute_attacks = value

    def update(self, warinfo=None):
        if warinfo is None:
            warinfo = self.coc_api.get_currentwar(self.clan_tag)
        if warinfo.is_not_in_war():
            logger.debug('Not in a war.')
            if self.warinfo is not None:
                self.send_war_over_msg()
            self.reset()
            return

        self.populate_warinfo(warinfo)
        if warinfo.is_in_preparation():
            logger.debug('War preparation.')
            self.send_preparation_msg()
        elif warinfo.is_in_war():
            logger.debug('In a war.')
            self.send_war_msg()
            if not self.mute_attacks:
                self.send_attack_msgs()
        elif warinfo.is_war_over():
            logger.debug('War is over.')
            if self.archive:
                self.db.archive_war(self.get_war_id(), warinfo.data)
            if not self.mute_attacks:
                self.send_attack_msgs()
            self.send_war_over_msg()
            self.send_standings_msg()
            self.reset()
        else:
            print("Current war status is uknown. We stay quiet.")

    def populate_warinfo(self, warinfo):
        self.warinfo = warinfo
        self.warstats = WarStats(warinfo)
        self.msg_factory = MessageFactory(self.coc_api, warinfo)

    def get_war_id(self):
        if not self.warinfo:
            raise ValueError('Warinfo is empty.')
        return self.warinfo.create_war_id()

    def current_war_id(self):
        """The war under way, or None. Unlike `get_war_id` it may be asked
        before there is one, which is what subscribing needs."""
        return self.warinfo.create_war_id() if self.warinfo else None

    def send_preparation_msg(self):
        self.send_once(
            self.msg_factory.create_preparation_msg,
            msg_id='preparation_msg', kind='prep')
        self.send_once(
            self.msg_factory.create_players_msg,
            msg_id='players_msg', kind='prep')

    def send_war_msg(self):
        self.send_once(self.msg_factory.create_war_msg, 'war_msg', kind='prep')

    def send_attack_msgs(self):
        for order, items in sorted(self.warinfo.ordered_attacks.items()):
            player, attack = items
            self.send_single_attack_msg(player, attack)

    def send_single_attack_msg(self, player, attack):
        war_stats = self.warstats.calculate_war_stats_sofar(attack['order'])
        if self.warinfo.is_clan_member(player):
            self.send_clan_attack_msg(player, attack, war_stats)
        else:
            self.send_opponent_attack_msg(player, attack, war_stats)

    def send_clan_attack_msg(self, attacker, attack, war_stats):
        self.send_once(
            lambda: self.msg_factory.create_clan_attack_msg(
                attacker, attack, war_stats),
            msg_id=self.get_attack_id(attack), kind='attacks')
        if war_stats['clan_destruction'] == 100:
            self.send_once(
                lambda: self.msg_factory.create_clan_full_destruction_msg(
                    attacker, attack, war_stats),
                msg_id='clan_full_destruction', kind='attacks')

    def is_msg_sent(self, msg_id, chat_id):
        return self.db.is_sent(self.get_war_id(), msg_id, chat_id)

    def mark_msg_as_sent(self, msg_id, chat_id):
        self.db.mark_sent(self.get_war_id(), msg_id, chat_id)

    def get_attack_id(self, attack):
        return "attack{}{}".format(attack['attackerTag'][1:],
                                   attack['defenderTag'][1:])

    def send_opponent_attack_msg(self, attacker, attack, war_stats):
        self.send_once(lambda: self.msg_factory.create_opponent_attack_msg(
            attacker, attack, war_stats),
            msg_id=self.get_attack_id(attack), kind='attacks')
        if war_stats['op_destruction'] == 100:
            self.send_once(
                lambda: self.msg_factory.create_opponent_full_destruction_msg(
                    attacker, attack, war_stats),
                msg_id='op_full_destruction', kind='attacks')

    def send_war_over_msg(self):
        self.send_once(
            self.msg_factory.create_war_over_msg, msg_id='war_over_msg',
            kind='result')

    def send_standings_msg(self):
        """Post the table once per round, keyed to the round that ended."""
        if not self.leagueinfo:
            return
        rows = LeagueStandings(self.leagueinfo).rows()
        if rows:
            self.send_once(lambda: create_standings_msg(rows),
                           msg_id='standings_msg', kind='standings')

    def reset(self):
        self.warinfo = None
        self.warstats = None
        self.msg_factory = None

    def send_once(self, build, msg_id, kind='war'):
        """Send to every chat that has not had this message yet.

        Delivery is recorded per chat, so a chat added part way through a
        war is not held to what the others have already seen, and two
        clans meeting in the same war do not mark each other's messages
        as sent."""
        for chat_id in self.chat_ids:
            if self.is_msg_sent(msg_id, chat_id):
                continue
            if kind in self.db.muted_kinds(chat_id):
                # Marked without sending, so a chat that unmutes later
                # gets what happens next rather than the war it sat out.
                self.mark_msg_as_sent(msg_id, chat_id)
                continue
            i18n.activate(self.db.chat_lang(chat_id))
            self.notifier.send(build(), chat_id)
            # Only now: a send that raised must be tried again.
            self.mark_msg_as_sent(msg_id, chat_id)

    def send(self, msg, silent=False):
        """Tell every chat, without recording it. For news about the bot
        itself rather than about a war."""
        for chat_id in self.chat_ids:
            self.notifier.send(msg, chat_id, silent=silent)


if __name__ == '__main__':
    main()
