########################################################################
# Notifiers
########################################################################
import dataclasses
import json
import time

import requests

# Statuses that mean the bot is in the chat and can post there.
PRESENT = ('member', 'administrator', 'creator')

RETRIES = 3
RETRY_AFTER = 5


@dataclasses.dataclass
class Command:
    """Somebody asked the bot to do something."""
    chat_id: object
    from_id: object
    text: str
    chat_type: str = ''
    from_name: str = ''


@dataclasses.dataclass
class Membership:
    """The bot was added to a chat or removed from one.

    Being told rather than having to ask is what makes a channel usable:
    a channel post has no author, so the operator can never be recognised
    inside one and has to be handed its id somewhere else."""
    chat_id: object
    title: str
    chat_type: str
    joined: bool
    by_id: object = None


# Long enough that a quiet chat costs one request per interval, short
# enough that the war poll is not held up waiting behind it.
LONG_POLL = 10


class TelegramNotifier:
    def __init__(self, bot_token):
        self.bot_token = bot_token
        self.offset = None
        self._api = f'https://api.telegram.org/bot{bot_token}'

    def send(self, msg, chat_id, silent=False):
        endpoint = "https://api.telegram.org/bot{bot_token}/sendMessage?"\
                   "parse_mode={mode}&chat_id={chat_id}&text={text}"\
                   "&disable_notification={silent}"\
                   .format(bot_token=self.bot_token,
                           mode='HTML',
                           chat_id=chat_id,
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
        """Yield a Command or a Membership for each update worth acting on.

        This and `reply` are the inbound half of the seam that `send`
        already provides: a notifier for another chat service supplies
        its own and the commands themselves do not change.

        A post made in a channel arrives as `channel_post` rather than
        `message` and carries no author, so `from_id` is None there and
        nobody can be recognised as the operator from a channel.

        `my_chat_member` needs no asking for: getUpdates delivers it by
        default, unlike `chat_member` for other people."""
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
            event = self._as_event(update)
            if event is not None:
                yield event

    def _as_event(self, update):
        tap = update.get('callback_query')
        if tap:
            self._settle(tap)
            message = tap.get('message') or {}
            chat = message.get('chat') or {}
            sender = tap.get('from') or {}
            return Command(chat_id=chat.get('id'), from_id=sender.get('id'),
                           text=tap.get('data') or '',
                           chat_type=chat.get('type') or '',
                           from_name=sender.get('username')
                           or sender.get('first_name') or '')
        membership = update.get('my_chat_member')
        if membership:
            chat = membership['chat']
            status = membership['new_chat_member']['status']
            actor = membership.get('from') or {}
            return Membership(chat_id=chat['id'],
                              title=chat.get('title') or '',
                              chat_type=chat.get('type') or '',
                              joined=status in PRESENT,
                              by_id=actor.get('id'))
        message = update.get('message') or update.get('channel_post') or {}
        if message.get('text', '').startswith('/'):
            sender = message.get('from') or {}
            return Command(chat_id=message['chat']['id'],
                           from_id=sender.get('id'), text=message['text'],
                           chat_type=message['chat'].get('type') or '',
                           from_name=sender.get('username')
                           or sender.get('first_name') or '')
        return None

    def reply(self, chat_id, msg, choices=()):
        """Answer, optionally offering choices as buttons.

        A choice carries the command it stands for, so tapping it is the
        same as typing it: same handler, same permission check."""
        data = {'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'}
        if choices:
            data['reply_markup'] = json.dumps({'inline_keyboard': [
                [{'text': label, 'callback_data': command}
                 for label, command in choices]]})
        res = requests.post(f'{self._api}/sendMessage', data=data)
        res.raise_for_status()

    def publish_menu(self, commands, language_code=None, chat_id=None):
        """Put the commands in Telegram's own menu.

        The list lives beside the input box rather than in the chat, so
        nothing is posted. A scope of one chat is how the operator sees
        their commands and nobody else does."""
        data = {'commands': json.dumps(
            [{'command': name, 'description': text}
             for name, text in commands])}
        if language_code:
            data['language_code'] = language_code
        if chat_id is not None:
            data['scope'] = json.dumps({'type': 'chat', 'chat_id': chat_id})
        res = requests.post(f'{self._api}/setMyCommands', data=data)
        res.raise_for_status()

    def _settle(self, tap):
        """Stop Telegram's spinner and take the buttons away, so a
        settled request cannot be tapped a second time."""
        requests.post(f'{self._api}/answerCallbackQuery',
                      data={'callback_query_id': tap['id']})
        message = tap.get('message') or {}
        if message.get('message_id'):
            requests.post(f'{self._api}/editMessageReplyMarkup',
                          data={'chat_id': message['chat']['id'],
                                'message_id': message['message_id']})

    def _retry_after(self, res):
        return res.json().get('parameters', {}).get('retry_after', RETRY_AFTER)


class DummyNotifier:
    def send(self, msg, chat_id, silent=False):
        if not silent:
            print(msg)

    def receive(self):
        return []

    def reply(self, chat_id, msg, choices=()):
        print(msg)

    def publish_menu(self, commands, language_code=None, chat_id=None):
        pass
