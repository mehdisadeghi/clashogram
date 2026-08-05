########################################################################
# Notifiers
########################################################################
import time

import requests

RETRIES = 3
RETRY_AFTER = 5
# Long enough that a quiet chat costs one request per interval, short
# enough that the war poll is not held up waiting behind it.
LONG_POLL = 10


class TelegramNotifier:
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.offset = None
        self._api = f'https://api.telegram.org/bot{bot_token}'

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

    def receive(self):
        """Yield (chat_id, text) for each command sent to the bot.

        This and `reply` are the inbound half of the seam that `send`
        already provides: a notifier for another chat service supplies
        its own and the commands themselves do not change."""
        params = {'timeout': LONG_POLL}
        if self.offset is not None:
            params['offset'] = self.offset
        res = requests.get(f'{self._api}/getUpdates', params=params,
                           timeout=LONG_POLL * 2)
        res.raise_for_status()
        updates = res.json()['result']
        if updates:
            self.offset = updates[-1]['update_id'] + 1
        for update in updates:
            message = update.get('message') or {}
            if message.get('text', '').startswith('/'):
                yield message['chat']['id'], message['text']

    def reply(self, chat_id, msg):
        requests.post(f'{self._api}/sendMessage',
                      data={'chat_id': chat_id, 'text': msg,
                            'parse_mode': 'HTML'})

    def _retry_after(self, res):
        return res.json().get('parameters', {}).get('retry_after', RETRY_AFTER)


class DummyNotifier:
    def send(self, msg, silent=False):
        if not silent:
            print(msg)

    def receive(self):
        return []

    def reply(self, chat_id, msg):
        print(msg)
