########################################################################
# Commands
########################################################################
import gettext

from .formatters import (
    create_player_stats_msg,
    create_standings_msg,
    create_unused_attacks_msg,
)
from .models import LeaguePlayerStats, LeagueStandings, unused_attacks

_ = gettext.gettext


class CommandBot:
    """Turns a command into an answer. It never starts a conversation.

    Everything the monitor sends reports something that happened. These
    only reply, so nobody is interrupted by the bot deciding they ought
    to be told something.

    There is no transport in here on purpose: `answer` takes text and
    returns text, so a notifier for another chat service can drive it
    unchanged."""

    def __init__(self, monitor):
        self.monitor = monitor

    def answer(self, text):
        name = text.split()[0].lstrip('/').split('@')[0]
        handler = getattr(self, f'_cmd_{name}', None)
        if handler is None:
            return _('Unknown command. Try /help.')
        return handler()

    def _cmd_help(self):
        return _('/war, /missing, /standings, /stats, /clan, /help')

    def _cmd_war(self):
        if self.monitor.warinfo is None:
            return _('Not in a war.')
        return self.monitor.msg_factory.create_war_over_msg()

    def _cmd_missing(self):
        if self.monitor.warinfo is None:
            return _('Not in a war.')
        return create_unused_attacks_msg(unused_attacks(self.monitor.warinfo))

    def _cmd_standings(self):
        if self.monitor.leagueinfo is None:
            return _('Not in a league war.')
        return create_standings_msg(
            LeagueStandings(self.monitor.leagueinfo).rows())

    def _cmd_stats(self):
        if self.monitor.leagueinfo is None:
            return _('Not in a league war.')
        return create_player_stats_msg(
            LeaguePlayerStats(self.monitor.leagueinfo).rows())

    def _cmd_clan(self):
        claninfo = self.monitor.coc_api.get_claninfo(self.monitor.clan_tag)
        return _('War win streak {streak} {flag}').format(
            streak=claninfo.winstreak, flag=claninfo.country_flag_imoji)
