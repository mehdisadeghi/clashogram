########################################################################
# Notifiers
########################################################################
import requests


class TelegramNotifier(object):
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, msg, silent=False):
        endpoint = "https://api.telegram.org/bot{bot_token}/sendMessage?"\
                   "parse_mode={mode}&chat_id={chat_id}&text={text}"\
                   "&disable_notification={silent}"\
                   .format(bot_token=self.bot_token,
                           mode='HTML',
                           chat_id=self.chat_id,
                           text=requests.utils.quote(msg),
                           silent=silent)
        requests.post(endpoint)


class DummyNotifier(object):
    def send(self, msg, silent=False):
        if not silent:
            print(msg)
