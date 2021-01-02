#!/usr/bin/env python
"""clashogram - Clash of Clans war moniting for telegram channels."""
import os
import time
import shelve
import gettext
import hashlib
import logging

import click

from .models import WarStats
from .formatters import MessageFactory
from .api import CoCAPI
from .notifiers import TelegramNotifier, DummyNotifier
from .utils import SimpleKVDB


gettext.bindtextdomain('messages',
                       localedir=os.path.join(
                           os.path.dirname(os.path.realpath(__file__)),
                           'locales'))
gettext.textdomain('messages')
_ = gettext.gettext

POLL_INTERVAL = 60


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

    coc_api = CoCAPI(coc_token)
    notifier = TelegramNotifier(bot_token, chat_id)

    if dryrun:
        warlog = 'dryrun.db'
        notifier = DummyNotifier()

    with shelve.open(warlog, writeback=True) as db:
        dbwrapper = SimpleKVDB(db)
        monitor = WarMonitor(dbwrapper, coc_api, clan_tag, notifier)
        monitor.mute_attacks = mute_attacks
        try:
            monitor.start()
        finally:
            db.sync()
            db.close()


def serverless(db, coc_token, clan_tag, bot_token, chat_id):
    """Publish war updates to a telegram channel."""
    coc_api = CoCAPI(coc_token)
    notifier = TelegramNotifier(bot_token, chat_id)
    monitor = WarMonitor(db, coc_api, clan_tag, notifier)
    monitor.update()


########################################################################
# Main war monitor class
########################################################################

class WarMonitor(object):
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
        self._mute_attacks = False

    @property
    def mute_attacks(self):
        return self._mute_attacks

    @mute_attacks.setter
    def mute_attacks(self, value):
        self._mute_attacks = value

    def update(self, wartag=None):
        warinfo = self.coc_api.get_currentwar(self.clan_tag, wartag)
        # save_latest_data(warinfo.data, monitor)
        if warinfo.is_not_in_war():
            logging.debug('Not in a war.')
            if self.warinfo is not None:
                self.send_war_over_msg()
            self.reset()
            return

        self.populate_warinfo(warinfo)
        if warinfo.is_in_preparation():
            logging.debug('War preparation.')
            self.send_preparation_msg()
        elif warinfo.is_in_war():
            logging.debug('In a war.')
            self.send_war_msg()
            if not self.mute_attacks:
                self.send_attack_msgs()
        elif warinfo.is_war_over():
            logging.debug('War is over.')
            if not self.mute_attacks:
                self.send_attack_msgs()
            self.send_war_over_msg()
            self.reset()
        else:
            print("Current war status is uknown. We stay quiet.")

    def populate_warinfo(self, warinfo):
        self.warinfo = warinfo
        self.warstats = WarStats(warinfo)
        self.msg_factory = MessageFactory(self.coc_api, warinfo)
        if self.get_war_id() not in self.db:
            self.db[self.get_war_id()] = {}

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
        return self.db[self.get_war_id()].get(msg_id, False)

    def mark_msg_as_sent(self, msg_id):
        tmp = self.db[self.get_war_id()]
        tmp[msg_id] = True
        self.db[self.get_war_id()] = tmp

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
                if leagueinfo:
                    current_war_tag = leagueinfo.get_current_wartag()
                    next_war_tag = leagueinfo.get_next_wartag()
                    if current_war_tag:
                        self.update(wartag=current_war_tag)
                    if next_war_tag:
                        self.update(wartag=next_war_tag)
                else:
                    self.update()
                time.sleep(POLL_INTERVAL)
            except Exception as err:
                if '403' in str(err):
                    # Check whether warlog is public
                    if not self.coc_api.get_claninfo(self.clan_tag).is_warlog_public:
                        print('Warlog must be public. Exiting.')
                        self.notifier.send(_("Warlog must be public boss! ☠️"))
                elif '500' in str(err):
                    print('CoC internal server error, retrying.')
                    # self.notifier.send(
                    #     'CoC internal server error, retrying in {} seconds.'
                    #     .format(POLL_INTERVAL * 10), silent=True)
                    time.sleep(POLL_INTERVAL * 10)
                    continue
                elif '502' in str(err):
                    print('CoC bad gateway, retrying.')
                    # self.notifier.send(
                    #     'CoC bad gateway, retrying in {} seconds.'
                    #     .format(POLL_INTERVAL * 10), silent=True)
                    time.sleep(POLL_INTERVAL * 10)
                    continue
                elif '503' in str(err):
                    print('CoC maintenance error, retrying.')
                    self.notifier.send(
                        'CoC maintenance error, retrying in {} seconds.'
                        .format(POLL_INTERVAL * 10), silent=True)
                    time.sleep(POLL_INTERVAL * 10)
                    continue
                elif '504' in str(err):
                    print('504 Gateway Timeout, retrying.')
                    # self.notifier.send(
                    #     '504 Gateway Timeout, retrying in {} seconds.'
                    #     .format(POLL_INTERVAL * 10), silent=True)
                    time.sleep(POLL_INTERVAL * 10)
                    continue

                else:
                    self.notifier.send(
                        _("☠️ 😵 App is broken boss! Come over and fix me please!"))
                raise


if __name__ == '__main__':
    main()
