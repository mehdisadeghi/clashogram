########################################################################
# Message formatters
########################################################################
import gettext
import locale
import os

import jdatetime
import pytz
from dateutil.parser import parse as dateutil_parse

from .models import WarStats

_ = gettext.gettext


def create_standings_msg(rows):
    msg = "🏆" + _(" League standings")
    msg += "\n▪️" + _("Rank, stars, destruction, rounds, clan")
    width = max(len(row['name']) for row in rows)
    for rank, row in enumerate(rows, 1):
        msg += "\n▫️{rank: <2} {stars: <3} {destruction: >7.2f}% {rounds} " \
               "{name: <{width}}".format(rank=rank, width=width, **row)
    return "<pre>" + msg + "</pre>"


class MessageFactory:
    def __init__(self, coc_api, warinfo):
        self.coc_api = coc_api
        self.warinfo = warinfo
        self.warstats = WarStats(warinfo)

    def create_preparation_msg(self):
        msg_template = _("""{top_imoji} {war_size} fold war is ahead!
<pre>▫️ Clan {ourclan: <{cwidth}} L {ourlevel: <2} +{clanwinstreak} {clanloc}{clanflag}
▪️ Clan {opponentclan: <{cwidth}} L {theirlevel: <2} +{opwinstreak} {oploc}{opflag}</pre>
Game begins at {start}.
Have fun! {final_emoji}
""")
        clan_extra_info = self.get_clan_extra_info(self.warinfo.clan_tag)
        op_extra_info = self.get_clan_extra_info(self.warinfo.op_tag)

        ourclan = self.warinfo.clan_name
        opclan = self.warinfo.op_name

        msg = msg_template.format(
            top_imoji='\U0001F3C1',
            ourclan=ourclan,
            ourlevel=self.warinfo.clan_level,
            opponentclan=opclan,
            theirlevel=self.warinfo.op_level,
            ourtag=self.warinfo.clan_tag,
            opponenttag=self.warinfo.op_tag,
            start=self.format_time(self.warinfo.start_time),
            war_size=self.warinfo.team_size,
            final_emoji='\U0001F6E1',
            clanloc=clan_extra_info.location,
            clanflag=clan_extra_info.country_flag_imoji,
            oploc=op_extra_info.location,
            opflag=op_extra_info.country_flag_imoji,
            clanwinstreak=clan_extra_info.winstreak,
            opwinstreak=op_extra_info.winstreak,
            cwidth=max(len(ourclan), len(opclan)))
        # Appended rather than folded into the template above, which would
        # change its msgid and drop the existing fa and ru translations.
        if self.warinfo.is_hard_mode():
            msg += _('⚔️ This one is hard mode.')
        return msg

    def create_players_msg(self):
        msg = "⚪️" + _(" Players")
        msg += "\n▪️" + _("Position, TH, name")
        sorted_players_by_map_position = sorted(
            self.warinfo.clan_members.items(),
            key=lambda x: x[1]['mapPosition'])
        for player_tag, player_info in sorted_players_by_map_position:
            line = "▫️{map_position: <2d} {thlevel: <2d} {name}"\
                .format(thlevel=player_info['townhallLevel'],
                        map_position=player_info['mapPosition'],
                        name=player_info['name'])
            msg += "\n" + line

        return "<pre>" + msg + "</pre>"

    def create_war_msg(self):
        return _('War has begun!')

    def create_clan_full_destruction_msg(self, attacker, attack, war_stats):
        return _('⚪️ We destroyed them 100% boss!')

    def create_clan_attack_msg(self, member, attack, war_stats):
        return self.create_attack_msg(member, attack, war_stats,
                                      imoji='\U0001F535')

    def create_opponent_attack_msg(self, member, attack, war_stats):
        return self.create_attack_msg(member,
                                      attack, war_stats, imoji='\U0001F534')

    def create_attack_msg(self, member, attack, war_stats, imoji=''):
        msg_template = _("""<pre>{top_imoji} [{order}] {ourclan} vs {opponentclan}
Attacker: TH {attacker_thlevel: <2} MP {attacker_map_position} {attacker_name}
Defender: TH {defender_thlevel: <2} MP {defender_map_position} {defender_name}
Result: {stars} | {destruction_percentage}%
{war_info}
</pre>""")
        defender = self.warinfo.get_player_info(attack['defenderTag'])
        msg = msg_template.format(
            order=attack['order'],
            top_imoji=imoji,
            ourclan=self.warinfo.clan_name,
            opponentclan=self.warinfo.op_name,
            attacker_name=member['name'],
            attacker_thlevel=member['townhallLevel'],
            attacker_map_position=member['mapPosition'],
            defender_name=defender['name'],
            defender_thlevel=defender['townhallLevel'],
            defender_map_position=defender['mapPosition'],
            stars=self.format_star_msg(attack),
            destruction_percentage=attack['destructionPercentage'],
            war_info=self.create_war_info_msg(war_stats),
            nwidth=max(len(member['name']), len(defender['name'])))
        return msg

    def format_star_msg(self, attack):
        new_stars = self.warstats.get_attack_new_stars(attack)
        cookies = (attack['stars'] - new_stars) * '🍪'
        stars = new_stars * '⭐'
        return cookies + stars

    def create_war_info_msg(self, war_stats):
        template = _("""▪ {clan_attack_count: >{atkwidth}}/{total} ⭐ {clan_stars: <{swidth}} ⚡ {clan_destruction:.2f}%
▪ {opponent_attack_count: >{atkwidth}}/{total} ⭐ {opponent_stars: <{swidth}} ⚡ {opponent_destruction:.2f}%""")

        clan_stars = war_stats['clan_stars']
        op_stars = war_stats['op_stars']
        clan_attack_count = war_stats['clan_used_attacks']
        op_attack_count = war_stats['op_used_attacks']

        return template.format(
            total=self.warinfo.team_size * self.warinfo.attacks_per_member,
            clan_attack_count=clan_attack_count,
            opponent_attack_count=op_attack_count,
            clan_stars=clan_stars,
            clan_destruction=war_stats['clan_destruction'],
            opponent_stars=op_stars,
            opponent_destruction=war_stats['op_destruction'],
            swidth=len(str(max(clan_stars, op_stars))),
            atkwidth=len(str(max(clan_attack_count, op_attack_count))))

    def create_opponent_full_destruction_msg(self, attacker, attack,
                                             war_stats):
        return _('⚫️ They destroyed us 100% boss!')

    def create_war_over_msg(self):
        msg_template = _("""<pre>{win_or_lose_title}
Clan {ourclan: <{cwidth}} L {ourlevel: <2}
Clan {opponentclan: <{cwidth}} L {theirlevel: <2}
{war_info}
</pre>""")

        ourclan = self.warinfo.clan_name
        opclan = self.warinfo.op_name
        msg = msg_template.format(
            win_or_lose_title=self.create_win_or_lose_title(),
            ourclan=ourclan,
            ourlevel=self.warinfo.clan_level,
            opponentclan=opclan,
            theirlevel=self.warinfo.op_level,
            war_info=self.create_war_info_msg(
                self.warstats.get_latest_war_stats()),
            cwidth=max(len(ourclan), len(opclan)))
        return msg

    def create_win_or_lose_title(self):
        if self.warinfo.is_win():
            return "{} {}".format('🎉', _('We won!'))
        elif self.warinfo.is_draw():
            return "{} {}".format('🏳', _('It\'s a tie!'))
        else:
            return "{} {}".format('💩', _('We lost!'))

    def format_time(self, timestamp):
        utc_time = dateutil_parse(timestamp, fuzzy=True)
        langs = {locale.getlocale()[0],
                 os.environ.get('LANG'),
                 os.environ.get('LANGUAGE')}
        if langs.intersection(['fa_IR', 'fa', 'fa_IR.UTF-8', 'Persian_Iran']):
            tehran_time = utc_time.astimezone(pytz.timezone("Asia/Tehran"))
            fmt = jdatetime.datetime.fromgregorian(
                datetime=tehran_time,
                locale=jdatetime.FA_LOCALE).strftime("%a، %d %B %Y %H:%M:%S")
            return self.convert_to_persian_numbers(fmt)
        return utc_time.strftime("%a, %d %b %Y %H:%M:%S")

    def convert_to_persian_numbers(self, text):
        # Supper intelligent and super efficient :)
        return text.replace('0', '۰')\
                   .replace('1', '۱')\
                   .replace('2', '۲')\
                   .replace('3', '۳')\
                   .replace('4', '۴')\
                   .replace('5', '۵')\
                   .replace('6', '۶')\
                   .replace('7', '۷')\
                   .replace('8', '۸')\
                   .replace('9', '۹')

    def get_clan_extra_info(self, clan_tag):
        return self.coc_api.get_claninfo(clan_tag)
