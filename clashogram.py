#!/usr/bin/env python
"""clashogram - Clash of Clans war moniting for telegram channels."""
import os
import time
import json
import shelve
import locale

import jdatetime
import requests
import click
import pytz
from dateutil.parser import parse as dateutil_parse

locale.setlocale(locale.LC_ALL, "fa_IR")

POLL_INTERVAL = 2

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
        telegram_updater = TelegramUpdater(db, bot_token, channel_name)
        while True:
            try:
                wardata = get_currentwar(coc_token, clan_tag)
                #with open('sample.json', 'r') as f:
                #    wardata = json.loads(f.read())
                telegram_updater.update(wardata)
                save_wardata(wardata)
                time.sleep(POLL_INTERVAL)
            except (KeyboardInterrupt, SystemExit):
                db.close()
                raise
            except:
                telegram_updater.send("☠️ 😵 رئیس من ترکیدم! با آدمتون تماس بگیرید بیاد درستم کنه. قربان شما، ربات. 🤖")
                db.close()
                raise


def get_currentwar(coc_token, clan_tag):
    endpoint = get_currentwar_endpoint(clan_tag)
    res = requests.get(endpoint, headers={'Authorization': 'Bearer %s' % coc_token})
    if res.status_code == requests.codes.ok:
        return json.loads(res.content.decode('utf-8'))
    else:
        raise Exception('Error calling CoC API: %s' % res)


def get_currentwar_endpoint(clan_tag):
    return 'https://api.clashofclans.com/v1/clans/{clan_tag}/currentwar'.format(
            clan_tag=requests.utils.quote('#%s' % clan_tag))


def save_wardata(wardata):
    if wardata['state'] != 'notInWar':
        war_id = "{0}{1}".format(wardata['clan']['tag'][1:],
                                 wardata['preparationStartTime'])
        if not os.path.exists('warlog'):
            os.mkdir('warlog')
        path = os.path.join('warlog', war_id)
        json.dump(wardata, open(path, 'w'), ensure_ascii=False)
    

class TelegramUpdater(object):
    def __init__(self, db, bot_token, channel_name):
        self.db = db
        self.bot_token = bot_token
        self.channel_name = channel_name
        self.latest_wardata = None
        self.clan_members = {}
        self.opponent_members = {}
        self.players = {}
        self.ordered_attacks = None

    def update(self, wardata):
        if wardata['state'] == 'notInWar':
            self.send_war_over_msg()
            self.reset()
            return

        self.populate_warinfo(wardata)
        if self.is_in_preparation():
            self.send_preparation_msg()
        elif self.is_in_war():
            self.send_war_msg()
            self.send_attack_msgs()
        elif self.is_war_over():
            self.send_war_over_msg()
            self.reset()
        else:
            print("Current war status is uknown. We stay quiet.")

    def populate_warinfo(self, wardata):
        self.latest_wardata = wardata
        self.ordered_attacks = self.get_ordered_attacks()
        if self.get_war_id() not in self.db:
            self.initialize_war_entry()
        if self.is_new_war(wardata):
            for member in wardata['clan']['members']:
                self.clan_members[member['tag']] = member
                self.players[member['tag']] = member
            for opponent in wardata['opponent']['members']:
                self.opponent_members[opponent['tag']] = opponent
                self.players[opponent['tag']] = opponent

    def get_ordered_attacks(self):
        ordered_attacks = {}
        for player in self.players.values():
            for attack in self.get_player_attacks(player):
                ordered_attacks[attack['order']] = (player, attack)
        return ordered_attacks

    def initialize_war_entry(self):
        initial_db = {}
        self.db[self.get_war_id()] = initial_db

    def is_new_war(self, wardata):
        return self.create_war_id(wardata) in self.db

    def get_war_id(self):
        return self.create_war_id(self.latest_wardata)

    def create_war_id(self, wardata):
        return "{0}{1}".format(wardata['clan']['tag'],
                               wardata['preparationStartTime'])

    def is_in_preparation(self):
        return self.latest_wardata['state'] == 'preparation'

    def send_preparation_msg(self):
        if not self.is_preparation_msg_sent():
            msg = self.create_preparation_msg()
            self.send(msg)
            self.db[self.get_war_id()]['preparation_msg_sent'] = True
    
    def is_preparation_msg_sent(self):
        return self.db[self.get_war_id()].get('preparation_msg_sent', False)

    def create_preparation_msg(self):
        msg_template = """{top_imoji} {title}
کلن {ourclan} در برابر کلن {opponentclan}
تگ {ourtag} در برابر {opponenttag}
جنگ قبیله {start} شروع خواهد شد.
این وار {war_size} تائی است.
شاد باشید! {final_emoji}
"""
        msg = msg_template.format(top_imoji='\U0001F3C1',
                                  title='جنگ  در راه است!',
                                  ourclan=self.latest_wardata['clan']['name'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  ourtag=self.latest_wardata['clan']['tag'],
                                  opponenttag=self.latest_wardata['opponent']['tag'],
                                  start=self.format_time(self.latest_wardata['startTime']),
                                  war_size=self.latest_wardata['teamSize'],
                                  final_emoji='\U0001F6E1')
        return msg

    def format_time(self, timestamp):
        utc_time = dateutil_parse(timestamp, fuzzy=True)
        tehran_time = utc_time.astimezone(pytz.timezone("Asia/Tehran"))
        fmt = jdatetime.datetime.fromgregorian(datetime=tehran_time).strftime("%a، %d %b %Y %H:%M:%S")
        return convert_to_persian_numbers(fmt)

    def is_in_war(self):
        return self.latest_wardata['state'] == 'inWar'

    def send_war_msg(self):
        if not self.is_war_msg_sent():
            msg = self.create_war_msg()
            self.send(msg)
            self.db[self.get_war_id()]['war_msg_sent'] = True

    def is_war_msg_sent(self):
        return self.db[self.get_war_id()].get('war_msg_sent', False)

    def create_war_msg(self):
        return 'جنگ قبیله شروع شد!'

    def send_attack_msgs(self):
        for order, items in sorted(self.ordered_attacks.items()):
            player, attack = items
            self.send_single_attack_msg(player, attack)

    def send_single_attack_msg(self, player, attack):
        if self.is_clan_member(player):
            self.send_clan_attack_msg(player, attack)
        else:
            self.send_opponent_attack_msg(player, attack)

    def is_clan_member(self, player):
        return player['tag'] in self.clan_members

    def get_player_attacks(self, player):
        if 'attacks' in player:
            return  player['attacks']
        else:
            return []
    
    def send_clan_attack_msg(self, attacker, attack):
        if not self.is_attack_msg_sent(attack):
            msg = self.create_clan_attack_msg(attacker, attack)
            self.send(msg)
            self.db[self.get_war_id()][self.get_attack_id(attack)] = True

    def is_attack_msg_sent(self, attack):
        attack_id = self.get_attack_id(attack)
        return self.db[self.get_war_id()].get(attack_id, False)

    def create_clan_attack_msg(self, member, attack):
        msg_template = """<pre>{top_imoji} {order} کلن {ourclan} مقابل {opponentclan}
مهاجم: {attacker_name: <15} ت {attacker_thlevel: <2} ر {attacker_map_position}
مدافع: {defender_name: <15} ت {defender_thlevel: <2} ر {defender_map_position}
نتیجه: {stars}
تخریب: {destruction_percentage}%
{war_info}
</pre>"""

        defender = self.get_player_info(attack['defenderTag'])
        msg = msg_template.format(order=attack['order'],
                                  top_imoji='\U0001F535',
                                  ourclan=self.latest_wardata['clan']['name'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  attacker_name=member['name'],
                                  attacker_thlevel=member['townhallLevel'],
                                  attacker_map_position=member['mapPosition'],
                                  defender_name=defender['name'],
                                  defender_thlevel=defender['townhallLevel'],
                                  defender_map_position=defender['mapPosition'],
                                  stars=attack['stars'] * '⭐',
                                  destruction_percentage=attack['destructionPercentage'],
                                  war_info=self.create_war_info_msg())
        return msg

    def calculate_war_stats_sofar(self, attack_order=None):
        """CoC data is updated every 10 minutes and reflects stats after the last attack.
        We have to calculate the necesssary info for the previous ones"""
        info = {}
        info['clan_destruction'] = 0
        info['op_destruction'] = 0
        info['clan_stars'] = 0
        info['op_stars'] = 0
        info['clan_used_attacks'] = 0
        info['op_used_attacks'] = 0
        if not attack_order:
            attack_order = len(self.ordered_attacks)
        for order in range(1, attack_order + 1):
            player, attack = self.ordered_attacks[order]
            if self.is_clan_member(player):
                info['clan_destruction'] += self.get_attack_new_destruction(attack)
                info['clan_stars'] += self.get_attack_new_stars(attack)
                info['clan_used_attacks'] += 1
            else:
                info['op_destruction'] += self.get_attack_new_destruction(attack)
                info['op_stars'] += self.get_attack_new_stars(attack)
                info['op_used_attacks'] += 1
        info['op_destruction'] /= self.latest_wardata['teamSize']
        info['clan_destruction'] /= self.latest_wardata['teamSize']
        return info

    def get_attack_new_destruction(self, attack):
        if attack['destructionPercentage'] > self.get_best_attack_destruction(attack):
            return attack['destructionPercentage']
        else:
            return 0

    def get_best_attack_destruction(self, attack):
        defender = self.get_player_info(attack['defenderTag'])
        if 'bestOpponentAttack' in defender and defender['bestOpponentAttack']['attackerTag'] != attack['attackerTag']:
            return defender['bestOpponentAttack']['destructionPercentage']
        else:
            return 0

    def get_attack_new_stars(self, attack):
        existing_stars = self.get_best_attack_stars(attack)
        stars = attack['stars'] - existing_stars
        if stars > 0:
            return stars
        else:
            return 0

    def get_best_attack_stars(self, attack):
        defender = self.get_player_info(attack['defenderTag'])
        if 'bestOpponentAttack' in defender and defender['bestOpponentAttack']['attackerTag'] != attack['attackerTag']:
            return defender['bestOpponentAttack']['stars']
        else:
            return 0

    def create_war_info_msg(self):
        template = """▪ {clan_attack_count: <2}/{total} ⭐ {clan_stars: <3} ⚡ {clan_destruction:.2f}%
▪ {opponent_attack_count: <2}/{total} ⭐ {opponent_stars: <3} ⚡ {opponent_destruction:.2f}%"""
        return template.format(
            total=self.latest_wardata['teamSize'] * 2,
            clan_attack_count=self.latest_wardata['clan']['attacks'],
            opponent_attack_count=self.latest_wardata['opponent']['attacks'],
            clan_stars=self.latest_wardata['clan']['stars'],
            clan_destruction=self.latest_wardata['clan']['destructionPercentage'],
            opponent_stars=self.latest_wardata['opponent']['stars'],
            opponent_destruction=self.latest_wardata['opponent']['destructionPercentage'])

    def create_top_three_msg(self):
        # Check opponent's first three map positions for three star
        s1 = self.db[self.get_war_id()]['opponents_by_mapposition'][1]['stars']
        s2 = self.db[self.get_war_id()]['opponents_by_mapposition'][2]['stars']
        s3 = self.db[self.get_war_id()]['opponents_by_mapposition'][3]['stars']
        return "{}{}{}".format('✅' if s1 == 3 else '❌',
                               '✅' if s2 == 3 else '❌',
                               '✅' if s3 == 3 else '❌')

    def get_player_info(self, tag):
        if tag not in self.players:
            raise Exception('Player %s not found.' % tag)
        return self.players[tag]

    def get_attack_id(self, attack):
        return "attack{}{}".format(attack['attackerTag'][1:],    
                                   attack['defenderTag'][1:])

    def send_opponent_attack_msg(self, attacker, attack):
        if not self.is_attack_msg_sent(attack):
            msg = self.create_opponent_attack_msg(attacker, attack)
            self.send(msg)
            self.db[self.get_war_id()][self.get_attack_id(attack)] = True

    def create_opponent_attack_msg(self, member, attack):
        msg_template = """<pre>{top_imoji} {order} کلن {ourclan} مقابل {opponentclan}
مهاجم: {attacker_name: <15} ت {attacker_thlevel: <2} ر {attacker_map_position}
مدافع: {defender_name: <15} ت {defender_thlevel: <2} ر {defender_map_position}
نتیجه: {stars}
تخریب: {destruction_percentage}%
{war_info}
</pre>"""
        defender = self.get_player_info(attack['defenderTag'])
        msg = msg_template.format(order=attack['order'],
                                  top_imoji='\U0001F534',
                                  ourclan=self.latest_wardata['clan']['name'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  attacker_name=member['name'],
                                  attacker_thlevel=member['townhallLevel'],
                                  attacker_map_position=member['mapPosition'],
                                  defender_name=defender['name'],
                                  defender_thlevel=defender['townhallLevel'],
                                  defender_map_position=defender['mapPosition'],
                                  stars=attack['stars'] * '⭐',
                                  destruction_percentage=attack['destructionPercentage'],
                                  war_info=self.create_war_info_msg())
        return msg

    def is_war_over(self):
        return self.latest_wardata['state'] == 'warEnded'

    def send_war_over_msg(self):
        if not self.is_war_over_msg_sent():
            msg = self.create_war_over_msg()
            self.send(msg)
            self.db[self.get_war_id()]['war_over_msg_sent'] = True

    def is_war_over_msg_sent(self):
        return self.db[self.get_war_id()].get('war_over_msg_sent', False)

    def create_war_over_msg(self):
        msg_template = """<pre>{win_or_lose_title}
کلن {ourclan: <15} لول {ourlevel: <2} تخریب {descruction}% ⭐ {stars}
کلن {opponentclan: <15} لول {their_level: <2} تخریب {their_descruction}% ⭐ {their_stars}
{war_info}
</pre>"""

        msg = msg_template.format(win_or_lose_title=self.create_win_or_lose_title(),
                                  ourclan=self.latest_wardata['clan']['name'],
                                  descruction=self.latest_wardata['clan']['destructionPercentage'],
                                  ourlevel=self.latest_wardata['clan']['clanLevel'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  their_descruction=self.latest_wardata['opponent']['destructionPercentage'],
                                  their_level=self.latest_wardata['opponent']['clanLevel'],
                                  stars=self.latest_wardata['clan']['stars'],
                                  their_stars=self.latest_wardata['opponent']['stars'],
                                  their_destruction=self.latest_wardata['opponent']['destructionPercentage'],
                                  war_info=self.create_war_info_msg())
        return msg

    def create_win_or_lose_title(self):
        if self.did_we_win():
            return '\U0001F389 بردیم!'
        elif self.is_draw():
            return '🏳 مساوی کردیم.'
        else:
            return '💩 ریدیم!'

    def did_we_win(self):
        if self.latest_wardata['clan']['stars'] > self.latest_wardata['opponent']['stars']:
            return True
        elif self.latest_wardata['clan']['stars'] == self.latest_wardata['opponent']['stars'] and\
             self.latest_wardata['clan']['destructionPercentage'] > self.latest_wardata['opponent']['destructionPercentage']:
            return True
        else:
            return False

    def is_draw(self):
        return self.latest_wardata['clan']['stars'] == self.latest_wardata['opponent']['stars'] and self.latest_wardata['clan']['destructionPercentage'] == self.latest_wardata['opponent']['destructionPercentage']

    def reset(self):
        self.latest_wardata = None
        self.clan_members = {}
        self.opponent_members = {}
        self.players = {}
        self.ordered_attacks = None

    def send(self, msg):
        endpoint = "https://api.telegram.org/bot{bot_token}/sendMessage?parse_mode={mode}&chat_id=@{channel_name}&text={text}".format(bot_token=self.bot_token, mode='HTML', channel_name=self.channel_name, text=requests.utils.quote(msg))
        requests.post(endpoint)


def convert_to_persian_numbers(text):
    # Supper intelligent and super efficient :)
    return text.replace('0', '۰').replace('1', '۱').replace('2', '۲').replace('3', '۳').replace('4', '۴').replace('5', '۵').replace('6', '۶').replace('7', '۷').replace('8', '۸').replace('9', '۹')


if __name__ == '__main__':
    main()