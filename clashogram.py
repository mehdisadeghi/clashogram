#!/usr/bin/env python
"""clashogram - Clash of Clans war moniting for telegram channels."""
import os
import time
import json
import shelve
import locale
import gettext
import platform
import hashlib

import jdatetime
import requests
import click
import pytz
from dateutil.parser import parse as dateutil_parse
from requests.adapters import HTTPAdapter

gettext.bindtextdomain('messages', localedir=os.path.join(os.curdir, 'locales'))
gettext.textdomain('messages')
_ = gettext.gettext

POLL_INTERVAL = 60

@click.command()
@click.option('--coc-token', help='CoC API token. Reads COC_API_TOKEN env var.', envvar='COC_API_TOKEN', prompt=True)
@click.option('--clan-tag', help='Tag of clan without hash. Reads COC_CLAN_TAG env var.',envvar='COC_CLAN_TAG', prompt=True)
@click.option('--bot-token', help='Telegram bot token. The bot must be admin on the channel. Reads TELEGRAM_BOT_TOKEN env var.',
              envvar='TELEGRAM_BOT_TOKEN', prompt=True)
@click.option('--channel-name', help='Name of telegram channel for updates. Reads TELEGRAM_CHANNEL env var.',   
              envvar='TELEGRAM_CHANNEL', prompt=True)
def main(coc_token, clan_tag, bot_token, channel_name):
    """Publish war updates to a telegram channel."""
    monitor_currentwar(coc_token, clan_tag, bot_token, channel_name)


def monitor_currentwar(coc_token, clan_tag, bot_token, channel_name):
    """Send war news to telegram channel."""
    with shelve.open('warlog.db', writeback=True) as db:
        coc_api = CoCAPI(coc_token)
        notifier = TelegramNotifier(bot_token, channel_name)
        monitor = WarMonitor(db, coc_api, notifier)
        while True:
            try:
                warinfo = coc_api.get_currentwar(clan_tag)
                save_latest_data(warinfo.data, monitor)
                monitor.update(warinfo)
                db.sync()
                time.sleep(POLL_INTERVAL)
            except (KeyboardInterrupt, SystemExit):
                db.sync()
                db.close()
                raise
            except Exception as err:
                if '503' in str(err):
                    print('COC maintenance error, ignoring.')
                    time.sleep(POLL_INTERVAL)
                    continue
                monitor.send(_("☠️ 😵 App is broken boss! Come over and fix me please!"))
                db.close()
                raise


def save_wardata(wardata):
    if wardata['state'] != 'notInWar':
        war_id = "{0}{1}".format(wardata['clan']['tag'][1:],
                                 wardata['preparationStartTime'])
        if not os.path.exists('warlog'):
            os.mkdir('warlog')
        path = os.path.join('warlog', war_id)
        json.dump(wardata, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    

def save_latest_data(wardata, monitor):
    if wardata:
        save_wardata(wardata)
        json.dump(wardata, open('latest_downloaded_wardata.json', 'w', encoding='utf-8'), ensure_ascii=False)

########################################################################
# Notifiers
########################################################################
class TelegramNotifier(object):
    def __init__(self, bot_token, channel_name):
        self.bot_token = bot_token
        self.channel_name = channel_name

    def send(self, msg):
        endpoint = "https://api.telegram.org/bot{bot_token}/sendMessage?parse_mode={mode}&chat_id=@{channel_name}&text={text}".format(
            bot_token=self.bot_token,
            mode='HTML',
            channel_name=self.channel_name,
            text=requests.utils.quote(msg))
        requests.post(endpoint)

########################################################################
# CoC API Calls
########################################################################

class CoCAPI(object):
    def __init__(self, coc_token):
        self.coc_token = coc_token

    def get_currentwar(self, clan_tag):
        return WarInfo(self.call_api(self.get_currentwar_endpoint(clan_tag)))

    def get_claninfo(self, clan_tag):
        return ClanInfo(self.call_api(self.get_claninfo_endpoint(clan_tag)))

    def call_api(self, endpoint):
        s = requests.Session()
        s.mount('https://api.clashofclans.com', HTTPAdapter(max_retries=5))
        res = s.get(endpoint, headers={'Authorization': 'Bearer %s' % self.coc_token})
        if res.status_code == requests.codes.ok:
            return json.loads(res.content.decode('utf-8'))
        else:
            raise Exception('Error calling CoC API: %s' % res)

    def get_currentwar_endpoint(self, clan_tag):
        return 'https://api.clashofclans.com/v1/clans/{clan_tag}/currentwar'.format(
                clan_tag=requests.utils.quote('#%s' % clan_tag))

    def get_claninfo_endpoint(self, clan_tag):
        return 'https://api.clashofclans.com/v1/clans/{clan_tag}'.format(
                clan_tag=requests.utils.quote(clan_tag))

########################################################################
# Models according to CoC API
########################################################################

class ClanInfo(object):
    def __init__(self, clandata):
        self.data = clandata

    def get_location(self):
        return self.data['location']['name']

    def get_country_flag_imoji(self):
        if self.data['location']['isCountry']:
            return self._get_country_flag_imoji(self.data['location']['countryCode'])
        elif self.data['location']['name'] == 'International':
            return '🌎' # The unicode character for planet earth, not empty string!
        else:
            return ''

    def _get_country_flag_imoji(self, country_code):
        return "{}{}".format(chr(127397 + ord(country_code[0])),
                             chr(127397 + ord(country_code[1])))

    def get_winstreak(self):
        return self.data['warWinStreak']


class WarInfo(object):
    def __init__(self, wardata):
        self.data = wardata
        self.clan_members = {}
        self.opponent_members = {}
        self.players = {}
        self.ordered_attacks = None
        self._populate()

    @property
    def state(self):
        return self.data['state']

    @property
    def clan_tag(self):
        return self.data['clan']['tag']

    @property
    def op_tag(self):
        return self.data['opponent']['tag']

    @property
    def clan_name(self):
        return self.data['clan']['name']

    @property
    def op_name(self):
        return self.data['opponent']['name']

    @property
    def clan_level(self):
        return self.data['clan']['clanLevel']

    @property
    def op_level(self):
        return self.data['opponent']['clanLevel']

    @property
    def clan_destruction(self):
        return self.data['clan']['destructionPercentage']

    @property
    def op_destruction(self):
        return self.data['opponent']['destructionPercentage']

    @property
    def clan_stars(self):
        return self.data['clan']['stars']

    @property
    def op_stars(self):
        return self.data['opponent']['stars']

    @property
    def clan_attacks(self):
        return self.data['clan']['attacks']

    @property
    def op_attacks(self):
        return self.data['opponent']['attacks']

    @property
    def start_time(self):
        return self.data['startTime']

    @property
    def team_size(self):
        return self.data['teamSize']

    def _populate(self):
        if self.is_not_in_war():
            return
        for member in self.data['clan']['members']:
            self.clan_members[member['tag']] = member
            self.players[member['tag']] = member
        for opponent in self.data['opponent']['members']:
            self.opponent_members[opponent['tag']] = opponent
            self.players[opponent['tag']] = opponent
        self.ordered_attacks = self.get_ordered_attacks()

    def get_ordered_attacks(self):
        ordered_attacks = {}
        for player in self.players.values():
            for attack in self.get_player_attacks(player):
                ordered_attacks[attack['order']] = (player, attack)
        return ordered_attacks

    def get_player_attacks(self, player):
        if 'attacks' in player:
            return  player['attacks']
        else:
            return []

    def get_player_info(self, tag):
        if tag not in self.players:
            raise Exception('Player %s not found.' % tag)
        return self.players[tag]

    def is_not_in_war(self):
        return self.data['state'] == 'notInWar'

    def is_in_preparation(self):
        return self.data['state'] == 'preparation'

    def is_in_war(self):
        return self.data['state'] == 'inWar'

    def is_war_over(self):
        return self.data['state'] == 'warEnded'

    def is_clan_member(self, player):
        return player['tag'] in self.clan_members

    def is_win(self):
        if self.data['clan']['stars'] > self.data['opponent']['stars']:
            return True
        elif self.data['clan']['stars'] == self.data['opponent']['stars'] and\
             self.data['clan']['destructionPercentage'] > self.data['opponent']['destructionPercentage']:
            return True
        else:
            return False

    def is_draw(self):
        return self.data['clan']['stars'] == self.data['opponent']['stars'] and self.data['clan']['destructionPercentage'] == self.data['opponent']['destructionPercentage']

    def create_war_id(self):
        return "{0}{1}{2}".format(self.data['clan']['tag'],
                                  self.data['opponent']['tag'],
                                  self.data['preparationStartTime'])

########################################################################
# War statistics
########################################################################

class WarStats(object):
    def __init__(self, warinfo):
        self.warinfo = warinfo

    def calculate_war_stats_sofar(self, attack_order):
        """CoC data is updated every 10 minutes and reflects stats after the last attack.
        We have to calculate the necesssary info for the previous ones"""
        info = {}
        info['clan_destruction'] = 0
        info['op_destruction'] = 0
        info['clan_stars'] = 0
        info['op_stars'] = 0
        info['clan_used_attacks'] = 0
        info['op_used_attacks'] = 0
        for order in range(1, attack_order + 1):
            player, attack = self.warinfo.ordered_attacks[order]
            if self.warinfo.is_clan_member(player):
                info['clan_destruction'] += self.get_attack_new_destruction(attack)
                info['clan_stars'] += self.get_attack_new_stars(attack)
                info['clan_used_attacks'] += 1
            else:
                info['op_destruction'] += self.get_attack_new_destruction(attack)
                info['op_stars'] += self.get_attack_new_stars(attack)
                info['op_used_attacks'] += 1
        info['op_destruction'] /= self.warinfo.team_size
        info['clan_destruction'] /= self.warinfo.team_size
        return info

    def get_latest_war_stats(self):
        return {'clan_destruction': self.warinfo.clan_destruction,
                'op_destruction': self.warinfo.op_destruction,
                'clan_stars': self.warinfo.clan_stars,
                'op_stars': self.warinfo.op_stars,
                'clan_used_attacks': self.warinfo.clan_attacks,
                'op_used_attacks': self.warinfo.op_attacks,}

    def get_attack_new_destruction(self, attack):
        if attack['destructionPercentage'] > self.get_best_attack_destruction_upto(attack):
            return attack['destructionPercentage'] - self.get_best_attack_destruction_upto(attack)
        else:
            return 0

    def get_best_attack_destruction(self, attack):
        defender = self.warinfo.get_player_info(attack['defenderTag'])
        if 'bestOpponentAttack' in defender and defender['bestOpponentAttack']['attackerTag'] != attack['attackerTag']:
            return defender['bestOpponentAttack']['destructionPercentage']
        else:
            return 0

    def get_best_attack_destruction_upto(self, in_attack):
        best_score = 0
        for order in range(1, in_attack['order'] + 1):
            player, attack = self.warinfo.ordered_attacks[order]
            if attack['defenderTag'] == in_attack['defenderTag'] and attack['destructionPercentage'] > best_score and attack['attackerTag'] != in_attack['attackerTag']:
                best_score = attack['destructionPercentage']
        return best_score

    def get_attack_new_stars(self, attack):
        existing_stars = self.get_best_attack_stars_upto(attack)
        stars = attack['stars'] - existing_stars
        if stars > 0:
            return stars
        else:
            return 0

    def get_best_attack_stars_upto(self, in_attack):
        best_score = 0
        for order in range(1, in_attack['order'] + 1):
            player, attack = self.warinfo.ordered_attacks[order]
            if attack['defenderTag'] == in_attack['defenderTag'] and attack['stars'] > best_score and attack['attackerTag'] != in_attack['attackerTag']:
                best_score = attack['stars']
        return best_score

########################################################################
# Message formatters
########################################################################

class MessageFactory(object):
    def __init__(self, coc_api, warinfo):
        self.coc_api = coc_api
        self.warinfo = warinfo
        self.warstats = WarStats(warinfo)

    def create_preparation_msg(self):
        msg_template = _("""{top_imoji} {war_size} fold war is ahead!
<pre>▫️ Clan {ourclan: <{cwidth}} L {ourlevel: <2} +{clanwinstreak} {clanloc}{clanflag}
▪️ Clan {opponentclan: <{cwidth}} L {theirlevel: <2} +{opwinstreak} {oploc}{opflag}</pre>
Game begins at {start}.
Have fun! {final_emoji}
""")
        clan_extra_info = self.get_clan_extra_info(self.warinfo.clan_tag)
        op_extra_info = self.get_clan_extra_info(self.warinfo.op_tag)

        ourclan = self.warinfo.clan_name
        opclan = self.warinfo.op_name

        msg = msg_template.format(top_imoji='\U0001F3C1',
                                  ourclan=ourclan,
                                  ourlevel=self.warinfo.clan_level,
                                  opponentclan=opclan,
                                  theirlevel=self.warinfo.op_level,
                                  ourtag=self.warinfo.clan_tag,
                                  opponenttag=self.warinfo.op_tag,
                                  start=self.format_time(self.warinfo.start_time),
                                  war_size=self.warinfo.team_size,
                                  final_emoji='\U0001F6E1',
                                  clanloc=clan_extra_info.get_location(),
                                  clanflag=clan_extra_info.get_country_flag_imoji(),
                                  oploc=op_extra_info.get_location(),
                                  opflag=op_extra_info.get_country_flag_imoji(),
                                  clanwinstreak=clan_extra_info.get_winstreak(),
                                  opwinstreak=op_extra_info.get_winstreak(),
                                  cwidth=max(len(ourclan), len(opclan)))
        return msg

    def create_players_msg(self):
        msg = "⚪️" + _(" Players")
        msg += "\n▪️" + _("Position, TH, name")
        sorted_players_by_map_position = sorted(self.warinfo.clan_members.items(), key=lambda x: x[1]['mapPosition'])
        for player_tag, player_info in sorted_players_by_map_position:
            line = "▫️{map_position: <2d} {thlevel: <2d} {name}".format(thlevel=player_info['townhallLevel'],
                                                                        map_position=player_info['mapPosition'],
                                                                        name=player_info['name'])
            msg += "\n" + line

        return "<pre>" + msg + "</pre>"

    def create_war_msg(self):
        return _('War has begun!')

    def create_clan_full_destruction_msg(self, attacker, attack, war_stats):
        return _('⚪️ We destroyed them 100% boss!')

    def create_clan_attack_msg(self, member, attack, war_stats):
        return self.create_attack_msg(member, attack, war_stats, imoji='\U0001F535')

    def create_opponent_attack_msg(self, member, attack, war_stats):
        return self.create_attack_msg(member, attack, war_stats, imoji='\U0001F534')

    def create_attack_msg(self, member, attack, war_stats, imoji=''):
        msg_template = _("""<pre>{top_imoji} [{order}] {ourclan} vs {opponentclan}
Attacker: TH {attacker_thlevel: <2} MP {attacker_map_position} {attacker_name}
Defender: TH {defender_thlevel: <2} MP {defender_map_position} {defender_name}
Result: {stars} | {destruction_percentage}%
{war_info}
</pre>""")
        defender = self.warinfo.get_player_info(attack['defenderTag'])
        msg = msg_template.format(order=attack['order'],
                                  top_imoji=imoji,
                                  ourclan=self.warinfo.clan_name,
                                  opponentclan=self.warinfo.op_name,
                                  attacker_name=member['name'],
                                  attacker_thlevel=member['townhallLevel'],
                                  attacker_map_position=member['mapPosition'],
                                  defender_name=defender['name'],
                                  defender_thlevel=defender['townhallLevel'],
                                  defender_map_position=defender['mapPosition'],
                                  stars=self.format_star_msg(attack),
                                  destruction_percentage=attack['destructionPercentage'],
                                  war_info=self.create_war_info_msg(war_stats),
                                  nwidth=max(len(member['name']), len(defender['name'])))
        return msg

    def format_star_msg(self, attack):
        new_stars = self.warstats.get_attack_new_stars(attack)
        cookies = (attack['stars'] - new_stars) * '🍪'
        stars = new_stars * '⭐'
        return cookies + stars

    def create_war_info_msg(self, war_stats):
        template = _("""▪ {clan_attack_count: >{atkwidth}}/{total} ⭐ {clan_stars: <{swidth}} ⚡ {clan_destruction:.2f}%
▪ {opponent_attack_count: >{atkwidth}}/{total} ⭐ {opponent_stars: <{swidth}} ⚡ {opponent_destruction:.2f}%""")

        clan_stars = war_stats['clan_stars']
        op_stars = war_stats['op_stars']
        clan_attack_count = war_stats['clan_used_attacks']
        op_attack_count = war_stats['op_used_attacks']

        return template.format(
            total=self.warinfo.team_size * 2,
            clan_attack_count=clan_attack_count,
            opponent_attack_count=op_attack_count,
            clan_stars=clan_stars,
            clan_destruction=war_stats['clan_destruction'],
            opponent_stars=op_stars,
            opponent_destruction=war_stats['op_destruction'],
            swidth=len(str(max(clan_stars, op_stars))),
            atkwidth=len(str(max(clan_attack_count, op_attack_count))))

    def create_opponent_full_destruction_msg(self, attacker, attack, war_stats):
        return _('⚫️ They destroyed us 100% boss!')

    def create_war_over_msg(self):
        msg_template = _("""<pre>{win_or_lose_title}
Clan {ourclan: <{cwidth}} L {ourlevel: <2}
Clan {opponentclan: <{cwidth}} L {theirlevel: <2}
{war_info}
</pre>""")

        ourclan = self.warinfo.clan_name
        opclan = self.warinfo.op_name
        msg = msg_template.format(win_or_lose_title=self.create_win_or_lose_title(),
                                  ourclan=ourclan,
                                  ourlevel=self.warinfo.clan_level,
                                  opponentclan=opclan,
                                  theirlevel=self.warinfo.op_level,
                                  war_info=self.create_war_info_msg(self.warstats.get_latest_war_stats()),
                                  cwidth=max(len(ourclan), len(opclan)))
        return msg

    def create_win_or_lose_title(self):
        if self.warinfo.is_win():
            return "{} {}".format('🎉', _('We won!'))
        elif self.warinfo.is_draw():
            return "{} {}".format('🏳', _('It\'s a tie!'))
        else:
            return "{} {}".format('💩', _('We lost!'))

    def format_time(self, timestamp):
        utc_time = dateutil_parse(timestamp, fuzzy=True)
        langs = set([locale.getlocale()[0],
                    os.environ.get('LANG'),
                    os.environ.get('LANGUAGE')])
        if langs.intersection(['fa_IR', 'fa', 'fa_IR.UTF-8', 'Persian_Iran']):
            self.setlocale_fa()
            tehran_time = utc_time.astimezone(pytz.timezone("Asia/Tehran"))
            fmt = jdatetime.datetime.fromgregorian(datetime=tehran_time).strftime("%a، %d %b %Y %H:%M:%S")
            return self.convert_to_persian_numbers(fmt)
        return utc_time.strftime("%a, %d %b %Y %H:%M:%S")

    def setlocale_fa(self):
        if platform.system() == 'Windows':
            locale.setlocale(locale.LC_ALL, 'Persian')
            self.patch_jdatetime()
        else:
            locale.setlocale(locale.LC_ALL, "fa_IR.UTF-8")

    def patch_jdatetime(self):
        jdatetime.date._is_fa_locale = lambda self: True

    def convert_to_persian_numbers(self, text):
        # Supper intelligent and super efficient :)
        return text.replace('0', '۰').replace('1', '۱').replace('2', '۲').replace('3', '۳').replace('4', '۴').replace('5', '۵').replace('6', '۶').replace('7', '۷').replace('8', '۸').replace('9', '۹')

    def get_clan_extra_info(self, clan_tag):
        return self.coc_api.get_claninfo(clan_tag)

########################################################################
# Main war monitor class
########################################################################

class WarMonitor(object):
    def __init__(self, db, coc_api, notifier):
        self.db = db
        self.coc_api = coc_api
        self.notifier = notifier
        self.warinfo = None
        self.msg_factory = None
        self.warstats = None

    def update(self, warinfo):
        if warinfo.is_not_in_war():
            if self.warinfo is not None:
                self.send_war_over_msg()
            self.reset()
            return

        self.populate_warinfo(warinfo)
        if warinfo.is_in_preparation():
            self.send_preparation_msg()
        elif warinfo.is_in_war():
            self.send_war_msg()
            self.send_attack_msgs()
        elif warinfo.is_war_over():
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
        self.send_once(self.msg_factory.create_preparation_msg(), msg_id='preparation_msg')
        self.send_once(self.msg_factory.create_players_msg(), msg_id='players_msg')
    
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
        self.send_once(self.msg_factory.create_clan_attack_msg(attacker, attack, war_stats),
            msg_id=self.get_attack_id(attack))
        if war_stats['clan_destruction'] == 100:
            self.send_once(self.msg_factory.create_clan_full_destruction_msg(attacker, attack, war_stats),
                msg_id='clan_full_destruction')

    def is_msg_sent(self, msg_id):
        return self.db[self.get_war_id()].get(msg_id, False)

    def mark_msg_as_sent(self, msg_id):
        self.db[self.get_war_id()][msg_id] = True

    def get_attack_id(self, attack):
        return "attack{}{}".format(attack['attackerTag'][1:],    
                                   attack['defenderTag'][1:])

    def send_opponent_attack_msg(self, attacker, attack, war_stats):
        self.send_once(self.msg_factory.create_opponent_attack_msg(attacker, attack, war_stats),
            msg_id=self.get_attack_id(attack))
        if war_stats['op_destruction'] == 100:
            self.send_once(self.msg_factory.create_opponent_full_destruction_msg(attacker, attack, war_stats),
                msg_id='op_full_destruction')

    def send_war_over_msg(self):
        self.send_once(self.msg_factory.create_war_over_msg(), msg_id='war_over_msg')

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


if __name__ == '__main__':
    main()
