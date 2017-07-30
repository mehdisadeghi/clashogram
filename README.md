# clashogram
Clash of Clans war moniting for telegram channels.

> NOTE: Clash of Clans API data is always 10 minutes behind the game events. This is not a bug in this program.

`clashogram` monitors your clan's warlog and posts the following messages to a Telegram channel:
1. Preparation started (with clans and players information)
2. War started
3. New attacks (with details)
4. War over


# Installation
From pypi:
```
pip install clashogram
```
From Github:
```
git clone https://github.com/mehdisadeghi/clashogram.git
cd clashogram
install -r requirements.txt
python setup.py install
```

# Usage
In order to use the program do the following:

1. Open a Clash of Clans developer account at https://developer.clashofclans.com/.
2. Find your external IP address using a website like [this](whatismyipaddress.com).
3. Go to your CoC developer page and create an API token for the IP number you just found.
4. Create a Telegram bot using BotFather and copy its token.
5. Create a new Telegram group and add the bot you just created as an administrator to that group.

Now you can run the following command:
```
pip install clashogram
clashogram --coc-token <COC_API_TOKEN> --clan-tag <CLAN_TAG> --bot-token <TELEGRAM_BOT_TOKEN> --channel-name <TELEGRAM_CHANNEL_NAME>
```

# Contribution (PRs welcome!)
The Telegram notification is isolated from the rest of the program. You can replace it with anything else to have your messages sent to somewhere else.

Fork and clone the repository and send a PR. Make sure tests pass beforehand:
```
python -m unittest discover
```
Or with `py.test`:
```
pip install pytest
py.test
```

Have fun!

# License
MIT
