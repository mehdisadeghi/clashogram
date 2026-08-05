#!/usr/bin/env python
"""clashogram - Clash of Clans war moniting for telegram channels."""
import gettext
import hashlib
import json
import logging
import os
import time

import click
import requests

from .api import CoCAPI
from .formatters import MessageFactory, create_standings_msg
from .models import LeagueStandings, WarStats
from .notifiers import DummyNotifier, TelegramNotifier
from .storage import Storage
from .storage import import_shelve as import_shelve_warlog

gettext.bindtextdomain('messages',
                       localedir=os.path.join(
                           os.path.dirname(os.path.realpath(__file__)),
                           'locales'))
gettext.textdomain('messages')
_ = gettext.gettext

POLL_INTERVAL = 60
logger = logging.getLogger(__name__)


@click.command()
@click.option('--coc-token',
              help='CoC API token. Reads COC_API_TOKEN env var.',
              envvar='COC_API_TOKEN',
              prompt=True)
@click.option('--clan-tag',
              help='Tag of clan without hash. Reads COC_CLAN_TAG env var.',
              envvar='COC_CLAN_TAG',
              prompt=True)
@click.option('--bot-token',
              help='Telegram bot token. The bot must be admin on the channel.'
                   ' Reads TELEGRAM_BOT_TOKEN env var.',
              envvar='TELEGRAM_BOT_TOKEN',
              prompt=True)
@click.option('--chat-id',
              help=('Numeric ID of a chat or name of a public channel with @.'
                    ' Reads COC_CHAT_ID env var.'),
              envvar='TELEGRAM_CHAT_ID',
              prompt=True)
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
def main(coc_token, clan_tag, bot_token, chat_id, mute_attacks, warlog,
         loglevel, dryrun):
    """Publish war updates to a telegram channel."""
    if loglevel:
        logging.basicConfig(level=loglevel)

    notifier = TelegramNotifier(bot_token, chat_id)

    if dryrun:
        warlog = 'dryrun.db'
        notifier = DummyNotifier()

    with Storage(warlog) as db:
        coc_api = CoCAPI(coc_token, cache=db)
        monitor = WarMonitor(db, coc_api, clan_tag, notifier)
        monitor.mute_attacks = mute_attacks
        monitor.start()


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
def import_warlog(shelve_path, warlog_path):
    """Import a pre-sqlite shelve warlog into a sqlite one."""
    with Storage(warlog_path) as db:
        click.echo(f'Imported {import_shelve_warlog(shelve_path, db)}'
                   ' messages.')


def serverless(db, coc_token, clan_tag, bot_token, chat_id):
    """Publish war updates to a telegram channel."""
    coc_api = CoCAPI(coc_token)
    notifier = TelegramNotifier(bot_token, chat_id)
    monitor = WarMonitor(db, coc_api, clan_tag, notifier)
    monitor.update()


########################################################################
# Main war monitor class
########################################################################

class WarMonitor:
    def __init__(self, db, api, tag, notifier):
        """Scan warlog for war updates.

        This is the top most class that puts everything together.
        Calling `start` method will block forever. Calling `update`
        will fetch one update, notify the changes and return.

        Arguments:
            db -- A persistant dictionary-like object.
            api -- Api object
            tag -- Clantag
            notifier -- Notifier object
        """
        self.db = db
        self.clan_tag = tag
        self.coc_api = api
        self.notifier = notifier
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

    def send_preparation_msg(self):
        self.send_once(
            self.msg_factory.create_preparation_msg(),
            msg_id='preparation_msg')
        self.send_once(
            self.msg_factory.create_players_msg(),
            msg_id='players_msg')

    def send_war_msg(self):
        self.send_once(self.msg_factory.create_war_msg(), 'war_msg')

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
            self.msg_factory.create_clan_attack_msg(
                attacker, attack, war_stats),
            msg_id=self.get_attack_id(attack))
        if war_stats['clan_destruction'] == 100:
            self.send_once(
                self.msg_factory.create_clan_full_destruction_msg(
                    attacker, attack, war_stats),
                msg_id='clan_full_destruction')

    def is_msg_sent(self, msg_id):
        return self.db.is_sent(self.get_war_id(), msg_id)

    def mark_msg_as_sent(self, msg_id):
        self.db.mark_sent(self.get_war_id(), msg_id)

    def get_attack_id(self, attack):
        return "attack{}{}".format(attack['attackerTag'][1:],
                                   attack['defenderTag'][1:])

    def send_opponent_attack_msg(self, attacker, attack, war_stats):
        self.send_once(self.msg_factory.create_opponent_attack_msg(
            attacker, attack, war_stats),
            msg_id=self.get_attack_id(attack))
        if war_stats['op_destruction'] == 100:
            self.send_once(
                self.msg_factory.create_opponent_full_destruction_msg(
                    attacker, attack, war_stats),
                msg_id='op_full_destruction')

    def send_war_over_msg(self):
        self.send_once(
            self.msg_factory.create_war_over_msg(), msg_id='war_over_msg')

    def send_standings_msg(self):
        """Post the table once per round, keyed to the round that ended."""
        if not self.leagueinfo:
            return
        rows = LeagueStandings(self.leagueinfo).rows()
        if rows:
            self.send_once(create_standings_msg(rows), msg_id='standings_msg')

    def reset(self):
        self.warinfo = None
        self.warstats = None
        self.msg_factory = None

    def send_once(self, msg, msg_id=None):
        if not msg_id:
            msg_id = hashlib.md5(msg.encode('utf-8')).hexdigest()

        if not self.is_msg_sent(msg_id):
            self.send(msg)
            self.mark_msg_as_sent(msg_id)

    def send(self, msg):
        self.notifier.send(msg)

    def start(self):
        """Send war news to telegram channel."""
        while True:
            try:
                leagueinfo = self.coc_api.get_currentleague(self.clan_tag)
                self.leagueinfo = leagueinfo
                if leagueinfo:
                    # These are already fetched, so they are not asked for
                    # a second time.
                    for previous_war in leagueinfo.get_previous_wars():
                        self.update(previous_war)
                    current_war = leagueinfo.get_current_war()
                    next_war = leagueinfo.get_next_war()
                    if current_war:
                        self.update(current_war)
                    if next_war:
                        self.update(next_war)
                else:
                    self.update()
                time.sleep(POLL_INTERVAL)
            except requests.HTTPError as err:
                status = err.response.status_code
                if status in (500, 502, 504):
                    print(f'CoC server error {status}, retrying.')
                    time.sleep(POLL_INTERVAL * 10)
                    continue
                elif status == 503:
                    print('CoC maintenance error, retrying.')
                    self.notifier.send(
                        f'CoC maintenance error, retrying in {POLL_INTERVAL * 10} seconds.'
                        , silent=True)
                    time.sleep(POLL_INTERVAL * 10)
                    continue
                elif status == 403:
                    # Check whether warlog is public
                    if not self.coc_api.get_claninfo(self.clan_tag).is_warlog_public:
                        print('Warlog must be public. Exiting.')
                        self.notifier.send(_("Warlog must be public boss! ☠️"))
                else:
                    self.notifier.send(
                        _("☠️ 😵 App is broken boss! Come over and fix me please!"))
                raise
            except Exception:
                self.notifier.send(
                    _("☠️ 😵 App is broken boss! Come over and fix me please!"))
                raise


if __name__ == '__main__':
    main()
