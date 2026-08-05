########################################################################
# Notifiers
########################################################################
import time

import requests


RETRIES = 3
RETRY_AFTER = 5


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
        for _ in range(RETRIES):
            res = requests.post(endpoint)
            if res.status_code != requests.codes.too_many_requests:
                break
            time.sleep(self._retry_after(res))
        # Raising leaves the message unmarked, so the next poll resends it.
        res.raise_for_status()

    def _retry_after(self, res):
        return res.json().get('parameters', {}).get('retry_after', RETRY_AFTER)


class DummyNotifier(object):
    def send(self, msg, silent=False):
        if not silent:
            print(msg)
