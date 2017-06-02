"""clashogram - Clash of Clans war moniting for telegram channels."""
import os
import time
import click
import json
import shelve
import requests

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
            telegram_updater.update(wardata)
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


class TelegramUpdater(object):
    def __init__(self, db, bot_token, channel_name):
        self.db = db
        self.bot_token = bot_token
        self.channel_name = channel_name
        self.latest_wardata = None

    def update(self, wardata):
        self.latest_wardata = wardata
        if self.get_war_id() not in self.db:
            self.db[self.get_war_id()] = {}
        if self.is_in_preparation():
            self.send_preparation_msg()
        elif self.is_in_war():
            self.send_war_msg()
        elif self.is_war_over():
            self.send_war_over_msg()
        else:
            print("Current war status is uknown. We stay quiet.")

    def get_war_id(self):
        return "{0}{1}".format(self.latest_wardata['clan']['tag'],
                               self.latest_wardata['preparationStartTime'])

    def is_in_preparation(self):
        print("state is %s" % self.latest_wardata['state'])
        return self.latest_wardata['state'] == 'inPreparation'

    def send_preparation_msg(self):
        if not self.is_preparation_msg_sent():
            msg = self.create_preparation_msg()
            self.send(msg)
            self.db[self.get_war_id()]['preparation_msg_sent'] = True
    
    def is_preparation_msg_sent(self):
        return self.db[self.get_war_id()].get('preparation_msg_sent', False)

    def create_preparation_msg(self):
        return 'preparation msg'

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
        return 'war message'

    def is_war_over():
        return self.latest_wardata['state'] == 'over'

    def send_war_over_msg():
        if not self.is_war_over_msg_sent():
            msg = self.create_war_over_msg()
            self.send(msg)
            self.db[self.get_war_id()]['war_over_msg_sent'] = True

    def is_war_over_msg_sent(self):
        return self.db[self.get_war_id()].get('war_over_msg_sent', False)

    def create_war_over_msg(self):
        return 'war over message'

    def send(self, msg):
        endpoint = "https://api.telegram.org/bot{bot_token}/sendMessage?parse_mode={mode}&chat_id=@{channel_name}&text={text}".format(bot_token=self.bot_token, mode='Markdown', channel_name=self.channel_name, text=msg)
        requests.post(endpoint)


if __name__ == '__main__':
    main(auto_envvar_prefix='CLASHOGRAM')

