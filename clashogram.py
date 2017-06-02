"""clashogram - Clash of Clans war moniting for telegram channels."""
import os
import time
import click
import json
import shelve
import requests
import jdatetime
import locale
import pytz
from dateutil.parser import parse as dateutil_parse

locale.setlocale(locale.LC_ALL, "fa_IR")

POLL_INTERVAL = 1

@click.command()
@click.option('--coc-token', help='CoC API token. Reads COC_API_TOKEN env var.', envvar='COC_API_TOKEN')
@click.option('--clan-tag', help='Tag of clan without hash. Reads COC_CLAN_TAG env var.',envvar='COC_CLAN_TAG')
@click.option('--bot-token', help='Telegram bot token. The bot must be admin on the channel. Reads TELEGRAM_BOT_TOKEN env var.',
              envvar='TELEGRAM_BOT_TOKEN')
@click.option('--channel-name', help='Name of telegram channel for updates. Reads TELEGRAM_CHANNEL env var.',
              envvar='TELEGRAM_CHANNEL')
def main(coc_token, clan_tag, bot_token, channel_name):
    """Publish war updates to a telegram channel."""
    monitor_currentwar(coc_token, clan_tag, bot_token, channel_name)


def monitor_currentwar(coc_token, clan_tag, bot_token, channel_name):
    """Send war news to telegram channel."""
    with shelve.open('warlog.db', writeback=True) as db:
        telegram_updater = TelegramUpdater(db, bot_token, channel_name)
        while True:
            wardata = get_currentwar(coc_token, clan_tag)
            print(wardata['state'])
            telegram_updater.update(wardata)
            save_wardata(wardata)
            time.sleep(POLL_INTERVAL)


def get_currentwar(coc_token, clan_tag):
    endpoint = get_currentwar_endpoint(clan_tag)
    res = requests.get(endpoint, headers={'Authorization': 'Bearer %s' % coc_token})
    if res.status_code == requests.codes.ok:
        return json.loads(res.content)
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

    def update(self, wardata):
        if wardata['state'] == 'notInWar':
            print('Not in war. Waiting.')
            return

        self.populate_warinfo(wardata)
        if self.is_in_preparation():
            self.send_preparation_msg()
        elif self.is_in_war():
            self.send_war_msg()
            self.send_attack_msgs()
        elif self.is_war_over():
            self.send_war_over_msg()
        else:
            print("Current war status is uknown. We stay quiet.")

    def populate_warinfo(self, wardata):
        self.latest_wardata = wardata
        if self.get_war_id() not in self.db:
            self.db[self.get_war_id()] = {}
        if self.is_new_war(wardata):
            for member in wardata['clan']['members']:
                self.clan_members[member['tag']] = member
                self.players[member['tag']] = member
            for opponent in wardata['opponent']['members']:
                self.opponent_members[opponent['tag']] = opponent
                self.players[opponent['tag']] = opponent

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
شاد باشید! {final_emoji}
"""
        msg = msg_template.format(top_imoji='\U0001F3C1',
                                  title='جنگ  در راه است!',
                                  ourclan=self.latest_wardata['clan']['name'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  ourtag=self.latest_wardata['clan']['tag'],
                                  opponenttag=self.latest_wardata['opponent']['tag'],
                                  start=self.format_time(self.latest_wardata['endTime']),
                                  final_emoji='\U0001F6E1')
        return msg

    def format_time(self, timestamp):
        utc_time = dateutil_parse(timestamp, fuzzy=True)
        tehran_time = utc_time.replace(tzinfo=pytz.timezone("Asia/Tehran"))
        fmt = jdatetime.datetime.fromgregorian(datetime=tehran_time).strftime("%a, %d %b %Y %H:%M:%S")
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
        return 'war start message'

    def send_attack_msgs(self):
        for member in self.clan_members.values():
            if 'attacks' in member:
                self.send_clan_attack_msg(member)
        for opponent in self.opponent_members.values():
            if 'attacks' in opponent:
                self.send_opponent_attack_msg(opponent)
    
    def send_clan_attack_msg(self, attacker):
        for attack in attacker['attacks']:
            if not self.is_attack_msg_sent(attack):
                msg = self.create_clan_attack_msg(attacker, attack)
                self.send(msg)
                self.db[self.get_war_id()][self.get_attack_id(attack)] = True

    def is_attack_msg_sent(self, attack):
        attack_id = self.get_attack_id(attack)
        return self.db[self.get_war_id()].get(attack_id, False)

    def create_clan_attack_msg(self, member, attack):
        msg_template = """{top_imoji} {title}
کلن {ourclan}\tدر برابر\tکلن {opponentclan}
تگ {ourtag}\tدر برابر\t{opponenttag}
مهاجم:\t{attacker_name}\tتاون {attacker_thlevel} رده {attacker_map_position}
در مصاف
مدافع:\t{defender_name}\tتاون ${defender_thlevel} رده {defender_map_position}
ستاره‌های قبلی:\t{previous_stars}\tستاره‌های جدید:\t{new_stars}
درصد تخریب: {destruction_percentage}%

شاد باشید!\t {final_emoji}
"""
        defender = self.get_player_info(attack['defenderTag'])
        msg = msg_template.format(top_imoji='\U0001F535',
                                  title='گزارش حمله! \U0001F692',
                                  ourclan=self.latest_wardata['clan']['name'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  ourtag=self.latest_wardata['clan']['tag'],
                                  opponenttag=self.latest_wardata['opponent']['tag'],
                                  attacker_name=member['name'],
                                  attacker_thlevel=member['townhallLevel'],
                                  attacker_map_position=member['mapPosition'],
                                  defender_name=defender['name'],
                                  defender_thlevel=defender['townhallLevel'],
                                  defender_map_position=defender['mapPosition'],
                                  previous_stars='?',
                                  new_stars=attack['stars'],
                                  destruction_percentage=attack['destructionPercentage'],
                                  final_emoji='\U0001F6E1')
        return msg

    def get_player_info(self, tag):
        if tag not in self.players:
            raise Exception('Player %s not found.' % tag)
        return self.players[tag]

    def get_attack_id(self, attack):
        return "attack{}{}".format(attack['attackerTag'][1:],
    
                                   attack['defenderTag'][1:])

    def send_opponent_attack_msg(self, attacker):
        for attack in attacker['attacks']:
            if not self.is_attack_msg_sent(attack):
                msg = self.create_opponent_attack_msg(attacker, attack)
                self.send(msg)
                self.db[self.get_war_id()][self.get_attack_id(attack)] = True

    def create_opponent_attack_msg(self, member, attack):
        msg_template = """{top_imoji} {title}
کلن {ourclan}\tدر برابر\tکلن {opponentclan}
تگ {ourtag}\tدر برابر\t{opponenttag}
مهاجم:\t{attacker_name}\tتاون {attacker_thlevel} رده {attacker_map_position}
در مصاف
مدافع:\t{defender_name}\tتاون ${defender_thlevel} رده {defender_map_position}
ستاره‌های قبلی:\t{previous_stars}\tستاره‌های جدید:\t{new_stars}
درصد تخریب: {destruction_percentage}%

شاد باشید!\t {final_emoji}
"""
        defender = self.get_player_info(attack['defenderTag'])
        msg = msg_template.format(top_imoji='\U0001F534',
                                  title='کلن زیر آتش! \U0001F691',
                                  ourclan=self.latest_wardata['clan']['name'],
                                  opponentclan=self.latest_wardata['opponent']['name'],
                                  ourtag=self.latest_wardata['clan']['tag'],
                                  opponenttag=self.latest_wardata['opponent']['tag'],
                                  attacker_name=member['name'],
                                  attacker_thlevel=member['townhallLevel'],
                                  attacker_map_position=member['mapPosition'],
                                  defender_name=defender['name'],
                                  defender_thlevel=defender['townhallLevel'],
                                  defender_map_position=defender['mapPosition'],
                                  previous_stars='?',
                                  new_stars=attack['stars'],
                                  destruction_percentage=attack['destructionPercentage'],
                                  final_emoji='\U0001F6E1')
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
        return 'war over message'

    def send(self, msg):
        print(msg)
        endpoint = "https://api.telegram.org/bot{bot_token}/sendMessage?parse_mode={mode}&chat_id=@{channel_name}&text={text}".format(bot_token=self.bot_token, mode='Markdown', channel_name=self.channel_name, text=requests.utils.quote(msg))
        print(endpoint)
        requests.post(endpoint)


def convert_to_persian_numbers(text):
    # Supper intelligent and super efficient :)
    return text.replace('0', '۰').replace('1', '۱').replace('2', '۲').replace('3', '۳').replace('4', '۴').replace('5', '۵').replace('6', '۶').replace('7', '۷').replace('8', '۸').replace('9', '۹')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(error)
        raise(error)

