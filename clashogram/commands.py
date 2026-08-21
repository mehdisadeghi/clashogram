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
import gettext
import html

import requests

from . import registry
from .formatters import (
    create_player_stats_msg,
    create_standings_msg,
    create_unused_attacks_msg,
)
from .models import LeaguePlayerStats, LeagueStandings, unused_attacks
from .notifiers import Membership

_ = gettext.gettext


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
                  event.chat_type)


def on_membership(ctx, event):
    """Tell the operator where the bot has just been put, or taken from.

    A channel post has no author, so the operator can never run a command
    inside a channel. Being handed the id here is what makes one usable
    at all."""
    if ctx.admin_id is None:
        return []
    title = html.escape(event.title)
    where = f'{event.chat_type} «{title}»' if event.title \
        else str(event.chat_type)
    if not event.joined:
        dropped = ctx.db.forget_chat(event.chat_id)
        return [(ctx.admin_id,
                 _('Removed from {where} ({chat}). Stopped following {count} '
                   'clan(s) there.').format(where=where, chat=event.chat_id,
                                            count=dropped))]
    return [(ctx.admin_id,
             _('Added to {where} ({chat}).\nTo follow a clan there:\n'
               '/add CLAN_TAG {chat}').format(where=where,
                                                chat=event.chat_id))]


def answer(ctx, chat_id, from_id, text, chat_type=''):
    """Answer one command as a list of (chat_id, message) pairs.

    More than one pair because approving a request tells both the
    operator and the chat that asked."""
    parts = text.split()
    name = parts[0].lstrip('/').split('@')[0]
    # Telegram puts the mention on the command, but people also type it
    # after an argument, and it is never part of one.
    args = [part.split('@')[0] for part in parts[1:]]

    if name == 'chatid':
        return [(chat_id, _chatid(ctx, chat_id, chat_type, from_id))]
    if name in OWNER_COMMANDS:
        if not _is_owner(ctx, from_id):
            return [(chat_id, _('Only the owner can do that.'))]
        return OWNER_COMMANDS[name](ctx, chat_id, args)
    if name in ADMIN_COMMANDS:
        if not _is_admin(ctx, from_id):
            return [(chat_id, _('Only an operator can do that.'))]
        return ADMIN_COMMANDS[name](ctx, chat_id, args)
    if name == 'request':
        return _cmd_request(ctx, chat_id, from_id, args)
    # Telegram sends /start itself, from the button it shows on first
    # contact, so it is the one command that has to answer for the bot.
    if name in ('help', 'start'):
        return [(chat_id, _usage(ctx, chat_id, from_id))]

    handler = WAR_COMMANDS.get(name)
    if handler is None:
        return [(chat_id, _('Unknown command. Try /help.'))]
    monitors = _monitors_for_chat(ctx, chat_id)
    if not monitors:
        return [(chat_id, _('This chat follows no clan yet.'))]
    if len(monitors) == 1:
        return [(chat_id, handler(monitors[0]))]
    return [(chat_id, '\n\n'.join(f'{m.clan_tag}\n{handler(m)}'
                                  for m in monitors))]


def _chatid(ctx, chat_id, chat_type, from_id):
    """The id, and what the asker can do with it. Telling everybody to
    run /add sends most of them at a command they cannot use."""
    lines = [_('This chat is {chat}.').format(chat=chat_id)]
    if chat_type == 'private':
        lines.append(_('Being a direct chat, that is also your user id.'))
    if _is_admin(ctx, from_id):
        lines += [_('To follow a clan here:'),
                  _('/add CLAN_TAG {chat}').format(chat=chat_id)]
    elif ctx.open_requests:
        lines += [_('To ask for a clan here:'),
                  _('/request CLAN_TAG')]
    return '\n'.join(lines)


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


def _usage(ctx, chat_id, from_id):
    """What this chat can ask for, and what it is following.

    Written out per chat rather than as one fixed list, because most of
    it is useless to the reader otherwise: the war commands say nothing
    until a clan is followed here, and the operator commands are noise
    to everybody but the operator."""
    followed = registry.clans_for_chat(ctx.db, chat_id)
    lines = [_('Clashogram follows Clash of Clans wars and reports them.'), '']

    if followed:
        lines += [_('This chat follows {clans}.').format(
            clans=', '.join(followed)), '',
            _('About the war:'),
            _('  /war        how it stands'),
            _('  /missing    who still has attacks'),
            _('  /standings  the league table'),
            _('  /stats      league attack stats'),
            _('  /clan       the clan itself')]
    else:
        lines.append(_('This chat follows no clan yet.'))
        # The operator is told how to fix that in their own section
        # below, so they are not sent to ask themselves.
        operator = _is_admin(ctx, from_id)
        if not operator and ctx.open_requests:
            lines += ['', _('To ask for one:'),
                      _('  /request CLAN_TAG    ask for a clan to be followed here')]
        elif not operator:
            lines.append(_('Requests are closed, so ask the operator.'))

    lines += ['', _('Anywhere:'),
              _('  /chatid     this chat\'s id; in a direct chat with the'
                ' bot it is also your own user id'),
              _('  /help       this message')]

    if _is_owner(ctx, from_id):
        lines += ['', _('Owner:'),
                  _('  /operators              who may operate'),
                  _('  /addoperator USER_ID    let somebody help'),
                  _('  /removeoperator USER_ID stop letting them'),
                  _('They send /chatid to the bot in a direct chat to'
                    ' find their user id.')]
    if _is_admin(ctx, from_id):
        lines += ['', _('Operator:'),
                  _('  /clans                     what is followed where'),
                  _('  /add CLAN_TAG [CHAT]       follow a clan'),
                  _('  /remove CLAN_TAG [CHAT]    stop following')]
        # Advertising them while nobody can file one describes a
        # workflow that cannot happen.
        if ctx.open_requests:
            lines += [_('  /requests                  who has asked'),
                      _('  /approve ID, /deny ID      settle a request')]
        else:
            lines.append(
                _('Requests are closed, so only you add clans.'))
        lines += ['',
                  _('A channel post has no author, so operator commands do'
                    ' not work inside a channel. Add the bot there, then'
                    ' send /add here with the id it reports.')]
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
    return _('War win streak {streak} {flag}').format(
        streak=claninfo.winstreak, flag=claninfo.country_flag_imoji)


WAR_COMMANDS = {
    'war': _cmd_war,
    'missing': _cmd_missing,
    'standings': _cmd_standings,
    'stats': _cmd_stats,
    'clan': _cmd_clan,
}


########################################################################
# Operator commands
########################################################################

def _cmd_clans(ctx, chat_id, args):
    grouped = registry.clans_with_chats(ctx.db)
    if not grouped:
        return [(chat_id, _('No clan is followed.'))]
    lines = [f'{clan_tag} -> {", ".join(chats)}'
             for clan_tag, chats in sorted(grouped.items())]
    return [(chat_id, '\n'.join(lines))]


def _cmd_add(ctx, chat_id, args):
    if not args:
        return [(chat_id, _('Usage: /add CLAN_TAG [CHAT_ID]'))]
    clan_tag = _normalise(args[0])
    target = args[1] if len(args) > 1 else chat_id
    name = _clan_name(ctx, clan_tag)
    if name is None:
        return [(chat_id, _('No clan is tagged {clan}.').format(
            clan=clan_tag))]
    monitor = ctx.monitors.get(clan_tag)
    war_id = monitor.current_war_id() if monitor else None
    registry.subscribe(ctx.db, clan_tag, target, war_id)
    return [(chat_id, _('Following {name} ({clan}) in {chat}.').format(
        name=name, clan=clan_tag, chat=target))]


def _clan_name(ctx, clan_tag):
    """The clan's name, or None if CoC has never heard of the tag.

    A tag that does not exist used to be stored anyway. It then failed
    every poll for ever, which shows up nowhere but the log while /clans
    goes on claiming the clan is followed."""
    if ctx.coc_api is None:
        return clan_tag
    try:
        return html.escape(ctx.coc_api.get_claninfo(clan_tag).data['name'])
    except requests.HTTPError as err:
        if err.response.status_code == 404:
            return None
        raise


def _cmd_remove(ctx, chat_id, args):
    if not args:
        return [(chat_id, _('Usage: /remove CLAN_TAG [CHAT_ID]'))]
    clan_tag = _normalise(args[0])
    target = args[1] if len(args) > 1 else chat_id
    if not registry.unsubscribe(ctx.db, clan_tag, target):
        return [(chat_id, _('{clan} was not followed in {chat}.').format(
            clan=clan_tag, chat=target))]
    return [(chat_id, _('Stopped following {clan} in {chat}.').format(
        clan=clan_tag, chat=target))]


def _cmd_requests(ctx, chat_id, args):
    pending = registry.pending_requests(ctx.db)
    if not pending:
        return [(chat_id, _('Nothing is waiting.'))]
    lines = ['{id}. {clan_tag} in {chat_id}'.format(**request)
             for request in pending]
    return [(chat_id, '\n'.join(lines))]


def _cmd_approve(ctx, chat_id, args):
    return _resolve(ctx, chat_id, args, approved=True)


def _cmd_deny(ctx, chat_id, args):
    return _resolve(ctx, chat_id, args, approved=False)


def _resolve(ctx, chat_id, args, approved):
    if not args or not args[0].isdigit():
        return [(chat_id, _('Usage: /approve REQUEST_ID'))]
    request = registry.resolve_request(ctx.db, int(args[0]), approved)
    if request is None:
        return [(chat_id, _('No request is waiting under that number.'))]
    verdict = _('Approved {clan}.') if approved else _('Denied {clan}.')
    answers = [(chat_id, verdict.format(clan=request['clan_tag']))]
    if approved:
        answers.append((request['chat_id'],
                        _('Now following {clan} here.').format(
                            clan=request['clan_tag'])))
    return answers


def _cmd_operators(ctx, chat_id, args):
    lines = [_('{owner} (owner)').format(owner=ctx.admin_id)]
    lines += registry.operators(ctx.db)
    return [(chat_id, '\n'.join(lines))]


def _cmd_addoperator(ctx, chat_id, args):
    if not args or not args[0].lstrip('-').isdigit():
        return [(chat_id, _('Usage: /addoperator USER_ID'))]
    if str(args[0]) == str(ctx.admin_id):
        return [(chat_id, _('That is the owner already.'))]
    registry.add_operator(ctx.db, args[0])
    return [(chat_id, _('{who} can now operate.').format(who=args[0])),
            (args[0], _('You can now operate this bot. Send /help.'))]


def _cmd_removeoperator(ctx, chat_id, args):
    if not args:
        return [(chat_id, _('Usage: /removeoperator USER_ID'))]
    if str(args[0]) == str(ctx.admin_id):
        return [(chat_id, _('The owner stays.'))]
    if not registry.remove_operator(ctx.db, args[0]):
        return [(chat_id, _('{who} was not an operator.').format(
            who=args[0]))]
    return [(chat_id, _('{who} can no longer operate.').format(who=args[0]))]


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

def _cmd_request(ctx, chat_id, from_id, args):
    if not ctx.open_requests:
        return [(chat_id, _('This instance is not taking requests.'))]
    if not args:
        return [(chat_id, _('Usage: /request CLAN_TAG'))]
    clan_tag = _normalise(args[0])
    name = _clan_name(ctx, clan_tag)
    if name is None:
        return [(chat_id, _('No clan is tagged {clan}.').format(
            clan=clan_tag))]
    request_id = registry.file_request(ctx.db, clan_tag, chat_id, from_id)
    if request_id is None:
        return [(chat_id, _('That is already waiting.'))]
    answers = [(chat_id, _('Sent. You will hear back once somebody has '
                           'looked at it.'))]
    if ctx.admin_id is not None:
        answers.append((ctx.admin_id,
                        _('{name} ({clan}) was asked for in {chat}.\n'
                          '/approve {id} or /deny {id}').format(
                            name=name, clan=clan_tag, chat=chat_id,
                            id=request_id)))
    return answers
