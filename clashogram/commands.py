########################################################################
# Commands
########################################################################
"""Turns a command into answers. It never starts a conversation.

Everything the monitor sends reports something that happened. These
only reply, so nobody is interrupted by the bot deciding they ought to
be told something.

There is no transport in here on purpose: `answer` takes text and
returns text addressed to a chat, so a notifier for another chat
service can drive it unchanged."""
import dataclasses
import html

import requests

from . import i18n, registry
from .formatters import (
    create_player_stats_msg,
    create_standings_msg,
    create_unused_attacks_msg,
)
from .i18n import gettext_ as _
from .models import LeaguePlayerStats, LeagueStandings, unused_attacks
from .notifiers import Membership


@dataclasses.dataclass
class Answer:
    """Something to say, and optionally the choices that go with it.

    A choice is a label and the command it stands for. Rendering them is
    the notifier's business; another chat service may show them however
    it likes, or not at all."""
    chat_id: object
    text: str
    choices: tuple = ()


@dataclasses.dataclass
class Context:
    db: object
    monitors: dict
    admin_id: object = None
    open_requests: bool = False
    coc_api: object = None


def handle(ctx, event):
    """Answer one inbound event as a list of (chat_id, message) pairs."""
    if isinstance(event, Membership):
        return on_membership(ctx, event)
    return answer(ctx, event.chat_id, event.from_id, event.text,
                  event.chat_type, event.from_name)


def on_membership(ctx, event):
    """Tell the operator where the bot has just been put, or taken from.

    A channel post has no author, so the operator can never run a command
    inside a channel. Being handed the id here is what makes one usable
    at all."""
    if ctx.admin_id is None:
        return []
    if event.joined and event.title:
        ctx.db.remember_chat_title(event.chat_id, event.title)
    if event.joined and event.by_id is not None:
        ctx.db.set_chat_steward(event.chat_id, event.by_id)
    where = f'{event.chat_type} «{_safe(event.title)}»' if event.title \
        else str(event.chat_type)
    if not event.joined:
        dropped = ctx.db.forget_chat(event.chat_id)
        return [Answer(ctx.admin_id,
                 _('Out of {where} ({chat}). Dropped {count} clan(s).').format(where=where, chat=event.chat_id,
                                            count=dropped))]
    return [Answer(ctx.admin_id,
             _('I am in {where} ({chat}).\nFollow a clan there:\n/add CLAN_TAG {chat}').format(where=where,
                                                chat=event.chat_id))]


def answer(ctx, chat_id, from_id, text, chat_type='', from_name=''):
    """Answer one command as a list of (chat_id, message) pairs.

    More than one pair because approving a request tells both the
    operator and the chat that asked."""
    i18n.activate(ctx.db.chat_lang(chat_id))
    # Free, since they are talking to us anyway. Only for people whose
    # name gets shown, so passers-by leave nothing behind.
    if from_name and _is_admin(ctx, from_id):
        ctx.db.note_person_name(from_id, from_name)
    parts = text.split()
    name = parts[0].lstrip('/').split('@')[0]
    # Telegram puts the mention on the command, but people also type it
    # after an argument, and it is never part of one.
    args = [part.split('@')[0] for part in parts[1:]]

    if name == 'mute':
        return _cmd_mute(ctx, chat_id, from_id, args)
    if name == 'lang':
        return _cmd_lang(ctx, chat_id, from_id, args)
    if name == 'chatid':
        return [Answer(chat_id, _chatid(ctx, chat_id, chat_type, from_id))]
    if name in OWNER_COMMANDS:
        if not _is_owner(ctx, from_id):
            return [_refuse(ctx, chat_id, from_id, owner_only=True)]
        return OWNER_COMMANDS[name](ctx, chat_id, args)
    if name in ADMIN_COMMANDS:
        if not _is_admin(ctx, from_id):
            return [_refuse(ctx, chat_id, from_id)]
        # Settling requests is an operator's job; deciding whether the
        # instance takes any at all is the owner's.
        if name == 'requests' and args and not _is_owner(ctx, from_id):
            return [_refuse(ctx, chat_id, from_id, owner_only=True)]
        return ADMIN_COMMANDS[name](ctx, chat_id, args)
    if name == 'request':
        return _cmd_request(ctx, chat_id, from_id, args, from_name)
    # Telegram sends /start itself, from the button it shows on first
    # contact, so it is the one command that has to answer for the bot.
    if name in ('help', 'start'):
        return [Answer(chat_id, _usage(ctx, chat_id, from_id, chat_type))]

    handler = WAR_COMMANDS.get(name)
    if handler is None:
        return [Answer(chat_id, _('Unknown command. Try /help.'))]
    monitors = _monitors_for_chat(ctx, chat_id)
    if not monitors:
        return [Answer(chat_id, _('No clan followed here yet.'))]
    if len(monitors) == 1:
        return [Answer(chat_id, handler(monitors[0]))]
    return [Answer(chat_id, '\n\n'.join(f'{m.clan_tag}\n{handler(m)}'
                                  for m in monitors))]


def _steward(ctx, chat_id, from_id):
    """Whoever put the bot in this chat, or asked for it. They decide
    this chat's options without operating the whole instance."""
    if from_id is None:
        return False
    return str(from_id) == str(ctx.db.chat_steward(chat_id))


# What a war produces, and what a chat can refuse. Attacks are the
# flood: two per member per war, against a handful for everything else.
KINDS = ('attacks', 'prep', 'standings', 'result')


def _cmd_mute(ctx, chat_id, from_id, args):
    muted = ctx.db.muted_kinds(chat_id)
    if args:
        if args[0] not in KINDS:
            return [Answer(chat_id, _('I post attacks, prep, standings and '
                                      'result.'))]
        if not (_is_admin(ctx, from_id) or _steward(ctx, chat_id, from_id)):
            return [Answer(chat_id, _('Only an operator or whoever added me '
                                      'here can change that.'))]
        muted = muted ^ {args[0]}
        ctx.db.set_muted_kinds(chat_id, muted)
    return [Answer(chat_id, _('Tap to turn a kind on or off.'),
                   tuple((f'{"🔕" if k in muted else "🔔"} {k}',
                          f'/mute {k}') for k in KINDS))]


def _cmd_lang(ctx, chat_id, from_id, args):
    if not args:
        return [Answer(chat_id, _('Which language?'),
                       tuple((name, f'/lang {code}')
                             for code, name in i18n.LANGUAGES.items()))]
    if args[0] not in i18n.LANGUAGES:
        return [Answer(chat_id, _('I do not speak that.'))]
    if not (_is_admin(ctx, from_id) or _steward(ctx, chat_id, from_id)):
        return [Answer(chat_id, _('Only an operator or whoever added me '
                                  'here can change that.'))]
    ctx.db.set_chat_lang(chat_id, args[0])
    i18n.activate(args[0])
    return [Answer(chat_id, _('Talking {lang} here now.').format(
        lang=i18n.LANGUAGES[args[0]]))]


def _chatid(ctx, chat_id, chat_type, from_id):
    """The id, and what the asker can do with it. Telling everybody to
    run /add sends most of them at a command they cannot use."""
    lines = [_('This chat is {chat}.').format(chat=chat_id)]
    if chat_type == 'private':
        lines.append(_('That is your own user id too.'))
    if _is_admin(ctx, from_id):
        lines += [_('To follow a clan here:'),
                  _('/add CLAN_TAG {chat}').format(chat=chat_id)]
    elif _requests_open(ctx):
        lines += [_('To ask for a clan here:'),
                  _('/request CLAN_TAG')]
    return '\n'.join(lines)


def _safe(value):
    """Anything the bot did not write itself.

    Replies go out with parse_mode=HTML, so a clan tag, a Telegram
    first name or a chat title is markup unless it is escaped. Escaping
    happens here, at the point of use, rather than on the way into the
    database: what is stored stays true."""
    return html.escape(str(value))


def _refuse(ctx, chat_id, from_id, owner_only=False):
    """Say why, and what to do instead.

    In a channel this is not about rank at all: the post carries no
    author, so nobody is recognised there, operator or not."""
    if from_id is None:
        return Answer(chat_id, _('No names on channel posts, so I cannot tell it is you boss! Send it to me directly and add this chat: {chat}').format(chat=chat_id))
    if owner_only:
        return Answer(chat_id, _('Owner only boss! Ask them.'))
    if _requests_open(ctx):
        return Answer(chat_id, _('Operators only! Ask for your clan instead: /request CLAN_TAG'))
    return Answer(chat_id, _('Operators only! Ask one to add your clan here.'))


def _who(ctx, user_id):
    if user_id is None:
        return _('somebody')
    known = ctx.db.person_names().get(str(user_id))
    return f'{_safe(known)} ({user_id})' if known else str(user_id)


def _where(ctx, chat_id, here=None):
    """Naming a chat by its number is unreadable when it is the one
    being spoken in."""
    if here is not None and str(chat_id) == str(here):
        return _('this chat ({chat})').format(chat=chat_id)
    known = ctx.db.chat_titles().get(str(chat_id))
    return f'«{_safe(known)}» ({chat_id})' if known else str(chat_id)


def _requests_open(ctx):
    """The flag is the default. The owner can change it over Telegram,
    which is the whole point of not having to touch the deployment."""
    stored = ctx.db.setting('open_requests')
    if stored is None:
        return ctx.open_requests
    return stored == 'on'


def _is_owner(ctx, from_id):
    """The one from configuration. Cannot be removed, and alone decides
    who else may operate, so a co-operator cannot unseat them."""
    return (ctx.admin_id is not None and from_id is not None
            and str(from_id) == str(ctx.admin_id))


def _is_admin(ctx, from_id):
    """A channel post carries no author, so nobody is anybody there."""
    if from_id is None:
        return False
    return _is_owner(ctx, from_id) or str(from_id) in registry.operators(ctx.db)


def _monitors_for_chat(ctx, chat_id):
    return [ctx.monitors[tag]
            for tag in registry.clans_for_chat(ctx.db, chat_id)
            if tag in ctx.monitors]


def _normalise(clan_tag):
    """Accept a tag typed without its hash.

    Configuration is strict about this because a wrong tag there fails
    the whole instance. Somebody typing into a chat is not, and Telegram
    turns a leading hash into a hashtag besides."""
    return clan_tag if clan_tag.startswith('#') else f'#{clan_tag}'


def _usage(ctx, chat_id, from_id, chat_type=''):
    """What this chat can ask for, and what it is following.

    Written out per chat rather than as one fixed list, because most of
    it is useless to the reader otherwise: the war commands say nothing
    until a clan is followed here, and the operator commands are noise
    to everybody but the operator."""
    followed = registry.clans_for_chat(ctx.db, chat_id)
    lines = [_('I follow Clash of Clans wars and post them here.'), '']

    if followed:
        lines += [_('Following {clans} here.').format(
            clans=', '.join(followed)), '',
            _('About the war:'),
            _('  /war        how it stands'),
            _('  /missing    who still has attacks'),
            _('  /standings  the league table'),
            _('  /stats      league attack stats'),
            _('  /clan       the clan itself'),
            _('  /leaders    who runs it')]
    else:
        lines.append(_('No clan followed here yet.'))
        # The operator is told how to fix that in their own section
        # below, so they are not sent to ask themselves.
        operator = _is_admin(ctx, from_id)
        if not operator and _requests_open(ctx):
            lines += ['', _('To ask for one:'),
                      _('  /request CLAN_TAG    ask for a clan here')]
        elif not operator:
            lines.append(_('Requests are closed. Ask an operator!'))

    if chat_type == 'channel':
        lines += ['', _('No names on channel posts, so I cannot tell who you are here. Anything that changes things, send to me directly and add this chat ({chat}).').format(chat=chat_id)]
    lines += ['', _('You can add me to a group or a channel too.'),
              '', _('Anywhere:'),
              _('  /chatid     this chat\'s id, and yours if we talk directly'),
              _('  /lang       pick the language here'),
              _('  /mute       choose what I post here'),
              _('  /help       this message')]

    if _is_owner(ctx, from_id):
        lines += ['', _('Owner:'),
                  _('  /operators              who may operate'),
                  _('  /addoperator USER_ID    let somebody help'),
                  _('  /removeoperator USER_ID stop letting them'),
                  _('  /requests open|close    take requests, or stop'),
                  _('They send me /chatid directly to find their user id.')]
    if _is_admin(ctx, from_id):
        lines += ['', _('Operator:'),
                  _('  /clans                     what is followed where'),
                  _('  /add CLAN_TAG [CHAT]       follow a clan'),
                  _('  /remove CLAN_TAG [CHAT]    stop following')]
        # Advertising them while nobody can file one describes a
        # workflow that cannot happen.
        if _requests_open(ctx):
            lines += [_('  /requests                  who has asked'),
                      _('  /approve ID, /deny ID      settle a request')]
        else:
            lines.append(
                _('Requests are closed, so clans are yours to add.'))
        lines += ['',
                  _('I cannot tell who posts in a channel. Add me there, then send /add here with the id I report.')]
    return '\n'.join(lines)


########################################################################
# War commands
########################################################################

def _cmd_war(monitor):
    if monitor.warinfo is None:
        return _('Not in a war.')
    return monitor.msg_factory.create_war_over_msg()


def _cmd_missing(monitor):
    if monitor.warinfo is None:
        return _('Not in a war.')
    return create_unused_attacks_msg(unused_attacks(monitor.warinfo))


def _cmd_standings(monitor):
    if monitor.leagueinfo is None:
        return _('Not in a league war.')
    return create_standings_msg(LeagueStandings(monitor.leagueinfo).rows())


def _cmd_stats(monitor):
    if monitor.leagueinfo is None:
        return _('Not in a league war.')
    return create_player_stats_msg(
        LeaguePlayerStats(monitor.leagueinfo).rows())


def _cmd_clan(monitor):
    claninfo = monitor.coc_api.get_claninfo(monitor.clan_tag)
    lines = [_('War win streak {streak} {flag}').format(
        streak=claninfo.winstreak, flag=claninfo.country_flag_imoji)]
    if claninfo.leader:
        lines.append(_('Leader {name}').format(
            name=_safe(claninfo.leader)))
    return '\n'.join(lines)


def _cmd_leaders(monitor):
    people = monitor.coc_api.get_claninfo(monitor.clan_tag).leaders
    if not people:
        return _('Nobody is listed.')
    return '\n'.join(
        (_('Leader {name}') if rank == 0 else _('Co-leader {name}')).format(
            name=_safe(name)) for rank, name in people)


WAR_COMMANDS = {
    'war': _cmd_war,
    'missing': _cmd_missing,
    'standings': _cmd_standings,
    'stats': _cmd_stats,
    'clan': _cmd_clan,
    'leaders': _cmd_leaders,
}


########################################################################
# Operator commands
########################################################################

def _cmd_clans(ctx, chat_id, args):
    grouped = registry.clans_with_chats(ctx.db)
    if not grouped:
        return [Answer(chat_id, _('No clans followed.'))]
    names = ctx.db.clan_names()
    answers = []
    for clan_tag, chats in sorted(grouped.items()):
        if clan_tag not in names:
            # Bootstrapped clans never passed through /add. One request,
            # cached, and remembered from then on.
            found = _clan_name(ctx, clan_tag)
            if found:
                ctx.db.remember_clan_name(clan_tag, found)
                names[clan_tag] = found
        known = names.get(clan_tag)
        label = f'{known} ({clan_tag})' if known else clan_tag
        for chat in chats:
            answers.append(Answer(
                chat_id,
                _('{clan} in {chat}').format(
                    clan=label, chat=_where(ctx, chat, chat_id)),
                ((_('Stop following'), f'/remove {clan_tag} {chat}'),)))
    return answers


def _cmd_add(ctx, chat_id, args):
    if not args:
        return [Answer(chat_id, _('Usage: /add CLAN_TAG [CHAT_ID]'))]
    clan_tag = _normalise(args[0])
    target = args[1] if len(args) > 1 else chat_id
    name = _clan_name(ctx, clan_tag)
    if name is None:
        return [Answer(chat_id, _('No clan with tag {clan}!').format(
            clan=_safe(clan_tag)))]
    monitor = ctx.monitors.get(clan_tag)
    war_id = monitor.current_war_id() if monitor else None
    ctx.db.remember_clan_name(clan_tag, name)
    registry.subscribe(ctx.db, clan_tag, target, war_id)
    return [Answer(chat_id, _('Following {name} ({clan}) in {chat}.').format(
        name=_safe(name), clan=_safe(clan_tag),
        chat=_where(ctx, target, chat_id)))]


def _clan_name(ctx, clan_tag):
    """The clan's name, or None if CoC has never heard of the tag.

    A tag that does not exist used to be stored anyway. It then failed
    every poll for ever, which shows up nowhere but the log while /clans
    goes on claiming the clan is followed."""
    if ctx.coc_api is None:
        return clan_tag
    try:
        return ctx.coc_api.get_claninfo(clan_tag).data['name']
    except requests.HTTPError as err:
        if err.response.status_code == 404:
            return None
        raise


def _cmd_remove(ctx, chat_id, args):
    if not args:
        return [Answer(chat_id, _('Usage: /remove CLAN_TAG [CHAT_ID]'))]
    clan_tag = _normalise(args[0])
    target = args[1] if len(args) > 1 else chat_id
    where = _where(ctx, target, chat_id)
    if not registry.unsubscribe(ctx.db, clan_tag, target):
        return [Answer(chat_id, _('{clan} was not followed in {chat}.').format(
            clan=_safe(clan_tag), chat=where))]
    return [Answer(chat_id, _('Stopped following {clan} in {chat}.').format(
        clan=_safe(clan_tag), chat=where))]


def _cmd_requests(ctx, chat_id, args):
    if args and args[0] in ('open', 'close'):
        ctx.db.set_setting('open_requests',
                           'on' if args[0] == 'open' else 'off')
        return [Answer(chat_id, _('Requests are open.') if args[0] == 'open'
                       else _('Requests are closed.'))]
    if args:
        return [Answer(chat_id, _('Usage: /requests [open|close]'))]
    pending = registry.pending_requests(ctx.db)
    if not pending:
        return [Answer(chat_id, _('Nothing waiting.'))]
    names = ctx.db.clan_names()
    return [Answer(chat_id,
                   _('{who} wants {name} ({clan}) in {chat}.').format(
                       who=_who(ctx, r['requester_id']),
                       name=names.get(r['clan_tag'], r['clan_tag']),
                       clan=r['clan_tag'], chat=_where(ctx, r['chat_id'])),
                   _settle_choices(r['id']))
            for r in pending]


def _settle_choices(request_id):
    return ((_('Approve'), f'/approve {request_id}'),
            (_('Deny'), f'/deny {request_id}'))


def _cmd_approve(ctx, chat_id, args):
    return _resolve(ctx, chat_id, args, approved=True)


def _cmd_deny(ctx, chat_id, args):
    return _resolve(ctx, chat_id, args, approved=False)


def _resolve(ctx, chat_id, args, approved):
    if not args or not args[0].isdigit():
        return [Answer(chat_id, _('Usage: /approve REQUEST_ID'))]
    request = registry.resolve_request(ctx.db, int(args[0]), approved)
    if request is None:
        return [Answer(chat_id, _('No request with that number.'))]
    clan = ctx.db.clan_names().get(request['clan_tag'], request['clan_tag'])
    if approved:
        told = _('{clan} is in! Its wars land here from now on.')
    else:
        told = _('{clan} was turned down.')
    return [Answer(chat_id, (_('Approved {clan}.') if approved
                             else _('Denied {clan}.')).format(clan=clan)),
            Answer(request['chat_id'], told.format(clan=clan))]


def _cmd_operators(ctx, chat_id, args):
    names = ctx.db.person_names()
    def label(user_id):
        known = names.get(str(user_id))
        return f'{known} ({user_id})' if known else str(user_id)
    lines = [_('{who} (owner)').format(who=label(ctx.admin_id))]
    lines += [label(o) for o in registry.operators(ctx.db)]
    return [Answer(chat_id, '\n'.join(lines))]


def _cmd_addoperator(ctx, chat_id, args):
    if not args or not args[0].lstrip('-').isdigit():
        return [Answer(chat_id, _('Usage: /addoperator USER_ID'))]
    if str(args[0]) == str(ctx.admin_id):
        return [Answer(chat_id, _('That is the owner!'))]
    registry.add_operator(ctx.db, args[0])
    return [Answer(chat_id, _('{who} can now operate.').format(who=_safe(args[0]))),
            Answer(args[0],
                   _('You are an operator now! Send /help.'))]


def _cmd_removeoperator(ctx, chat_id, args):
    if not args:
        return [Answer(chat_id, _('Usage: /removeoperator USER_ID'))]
    if str(args[0]) == str(ctx.admin_id):
        return [Answer(chat_id, _('The owner stays boss!'))]
    if not registry.remove_operator(ctx.db, args[0]):
        return [Answer(chat_id, _('{who} was not an operator.').format(
            who=_safe(args[0])))]
    return [Answer(chat_id, _('{who} can no longer operate.').format(who=_safe(args[0])))]


OWNER_COMMANDS = {
    'operators': _cmd_operators,
    'addoperator': _cmd_addoperator,
    'removeoperator': _cmd_removeoperator,
}

ADMIN_COMMANDS = {
    'clans': _cmd_clans,
    'add': _cmd_add,
    'remove': _cmd_remove,
    'requests': _cmd_requests,
    'approve': _cmd_approve,
    'deny': _cmd_deny,
}


########################################################################
# Asking to be followed
########################################################################

def _cmd_request(ctx, chat_id, from_id, args, from_name=''):
    if not _requests_open(ctx):
        return [Answer(chat_id, _('Not taking requests.'))]
    if not args:
        return [Answer(chat_id, _('Usage: /request CLAN_TAG'))]
    clan_tag = _normalise(args[0])
    name = _clan_name(ctx, clan_tag)
    if name is None:
        return [Answer(chat_id, _('No clan with tag {clan}!').format(
            clan=_safe(clan_tag)))]
    ctx.db.remember_clan_name(clan_tag, name)
    # Asking is not passing by: the operator has to know who to answer.
    if from_name:
        ctx.db.note_person_name(from_id, from_name)
    request_id = registry.file_request(ctx.db, clan_tag, chat_id, from_id)
    if request_id is None:
        return [Answer(chat_id, _('Already waiting.'))]
    answers = [Answer(chat_id, _('Asked! You will hear back.'))]
    if ctx.admin_id is not None:
        answers.append(Answer(ctx.admin_id,
                              _('{who} wants {name} ({clan}) in {chat}.').format(who=_who(ctx, from_id),
                                                  name=_safe(name),
                                                  clan=_safe(clan_tag),
                                                  chat=_where(ctx, chat_id)),
                              _settle_choices(request_id)))
    return answers
