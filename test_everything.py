'''Clashogram tests.'''
import gettext
import json
import os
import shelve
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from clashogram import commands, registry, runner
from clashogram.__main__ import WarMonitor
from clashogram.api import CoCAPI
from clashogram.formatters import MessageFactory
from clashogram.i18n import gettext_
from clashogram.models import (
    ClanInfo,
    LeagueInfo,
    LeaguePlayerStats,
    LeagueStandings,
    WarInfo,
    WarStats,
    unused_attacks,
)
from clashogram.notifiers import Membership, TelegramNotifier
from clashogram.storage import Storage, import_shelve


def load_wardata(name):
    with open(os.path.join('data', name), encoding='utf8') as fixture:
        return json.load(fixture)


class ClanInfoTestCase(unittest.TestCase):
    def setUp(self):
        self.claninfo = ClanInfo({'location': {'name': 'Iran',
                                               'isCountry': 'true',
                                               'countryCode': 'IR'},
                                  'warWinStreak': 0,
                                  'isWarLogPublic': True})

    def test_location(self):
        assert self.claninfo.location == 'Iran'

    def test_notset_location(self):
        claninfo = ClanInfo({})
        assert claninfo.location == ''
        assert claninfo.country_flag_imoji == ''

    def test_country_imoji(self):
        assert self.claninfo.country_flag_imoji == '🇮🇷'

    def test_winstreak(self):
        assert self.claninfo.winstreak == 0

    def test_is_warlog_public(self):
        assert self.claninfo.is_warlog_public == True


class WarInfoTestCase(unittest.TestCase):
    def setUp(self):
        self.warinfo = WarInfo(load_wardata('inWar_40.json'))
        self.op_member = {
            "tag": "#2GCR2YLP8",
            "name": "captain spock",
            "townhallLevel": 9,
            "mapPosition": 18,
            "opponentAttacks": 2,
            "bestOpponentAttack": {
                "attackerTag": "#G0QPL0LQ",
                "defenderTag": "#2GCR2YLP8",
                "stars": 3,
                "destructionPercentage": 100,
                "order": 78
            }
        }
        self.clan_member = {
            "tag": "#9QVR8R29C",
            "name": "VAHID",
            "townhallLevel": 7,
            "mapPosition": 35,
            "opponentAttacks": 2,
            "bestOpponentAttack": {
                "attackerTag": "#P0C92YP99",
                "defenderTag": "#9QVR8R29C",
                "stars": 3,
                "destructionPercentage": 100,
                "order": 3
            }
        }

    def test_start_time(self):
        assert self.warinfo.start_time == '20170603T191148.000Z'

    def test_team_size(self):
        assert self.warinfo.team_size == 40

    def test_get_ordered_attacks(self):
        ordered_attacks = self.warinfo.get_ordered_attacks()

        assert len(ordered_attacks) == 126

    def test_player_count(self):
        assert len(self.warinfo.players) == 80

    def test_get_player_attacks(self):
        player = self.warinfo.players['#2GCR2YLP8']

        assert self.warinfo.get_player_attacks(player) == []

    def test_get_player_info(self):
        with self.assertRaises(KeyError):
            self.warinfo.get_player_info('#2GCZZZZP8')

    def test_is_not_in_war(self):
        assert not self.warinfo.is_not_in_war()

    def test_is_in_preparation(self):
        assert not self.warinfo.is_in_preparation()

    def test_is_in_war(self):
        assert self.warinfo.is_in_war()

    def test_is_war_over(self):
        assert not self.warinfo.is_war_over()

    def test_is_clan_member(self):
        self.assertFalse(self.warinfo.is_clan_member(self.op_member))
        self.assertTrue(self.warinfo.is_clan_member(self.clan_member))

    def test_is_win(self):
        self.assertTrue(self.warinfo.is_win())

    def test_is_draw(self):
        self.assertFalse(self.warinfo.is_draw())

    def test_create_war_id(self):
        self.assertEqual(self.warinfo.create_war_id(),
                         "#YVL0C8UY#JC0L922Y20170602T201148.000Z")


class WarInfoNotInWarTestCase(unittest.TestCase):
    def setUp(self):
        self.warinfo = WarInfo(load_wardata('notInWar.json'))

    def test_clan_stats(self):
        self.assertEqual(self.warinfo.clan_level, 0)
        self.assertEqual(self.warinfo.clan_destruction, 0)
        self.assertEqual(self.warinfo.clan_stars, 0)
        self.assertEqual(self.warinfo.clan_attacks, 0)

    def test_op_stats(self):
        self.assertEqual(self.warinfo.op_level, 0)
        self.assertEqual(self.warinfo.op_destruction, 0)
        self.assertEqual(self.warinfo.op_stars, 0)
        self.assertEqual(self.warinfo.op_attacks, 0)

    def test_players(self):
        self.assertEqual(self.warinfo.players, {})


class LeagueWarPerspectiveTestCase(unittest.TestCase):
    """A league war may list us as the opponent rather than the clan."""
    def setUp(self):
        self.clan_tag = '#YVL0C8UY'
        self.wardata = load_wardata('cwl_warEnded_mirrored.json')

    def test_our_wartags_include_the_opponent_slot(self):
        leagueinfo = LeagueInfo(self.clan_tag,
                                {'rounds': [{'warTags': ['#WAR1']}]})
        api = MagicMock()
        api.get_currentwar.return_value = WarInfo(self.wardata, self.clan_tag)
        leagueinfo.populate_wartags(api)
        self.assertEqual(list(leagueinfo.our_wartags), ['#WAR1'])

    def test_reads_us_from_the_opponent_slot(self):
        warinfo = WarInfo(self.wardata, self.clan_tag)
        self.assertEqual(warinfo.clan_name, 'iran')
        self.assertEqual(warinfo.op_name, 'KINGS EMPIRE')
        self.assertFalse(warinfo.is_win())

    def test_attacks_per_member(self):
        regular = load_wardata('inWar_40.json')
        # A league war is one attack each, whatever the payload says.
        self.assertEqual(WarInfo(regular, self.clan_tag, '#WAR1')
                         .attacks_per_member, 1)
        # A regular war predating the field is two.
        self.assertEqual(WarInfo(regular, self.clan_tag).attacks_per_member, 2)
        # Otherwise trust the payload.
        self.assertEqual(WarInfo(self.wardata, self.clan_tag)
                         .attacks_per_member, 1)

    def test_is_hard_mode(self):
        regular = load_wardata('inWar_40.json')
        self.assertTrue(WarInfo(self.wardata, self.clan_tag).is_hard_mode())
        self.assertFalse(WarInfo(regular, self.clan_tag).is_hard_mode())

    def test_war_id_ignores_perspective(self):
        self.assertEqual(WarInfo(self.wardata, self.clan_tag).create_war_id(),
                         WarInfo(self.wardata).create_war_id())


class TelegramNotifierTestCase(unittest.TestCase):
    def _response(self, status_code, body=None):
        res = MagicMock()
        res.status_code = status_code
        res.json.return_value = body or {}
        res.raise_for_status.side_effect = (
            None if status_code == requests.codes.ok
            else requests.HTTPError(str(status_code)))
        return res

    def test_retries_after_rate_limit(self):
        notifier = TelegramNotifier('token')
        with patch('clashogram.notifiers.requests.post') as post, \
             patch('clashogram.notifiers.time.sleep') as sleep:
            post.side_effect = [
                self._response(429, {'parameters': {'retry_after': 7}}),
                self._response(200)]
            notifier.send('hi', 'chat')
            self.assertEqual(post.call_count, 2)
            sleep.assert_called_once_with(7)

    def test_undelivered_message_is_not_marked_sent(self):
        monitor = WarMonitor(Storage(':memory:'), MagicMock(), '#TAG',
                             MagicMock(), ['c1'])
        monitor.warinfo = MagicMock()
        monitor.warinfo.create_war_id.return_value = 'W1'
        monitor.notifier.send.side_effect = requests.HTTPError('429')
        with self.assertRaises(requests.HTTPError):
            monitor.send_once(lambda: 'hi', msg_id='m1')
        self.assertFalse(monitor.is_msg_sent('m1', 'c1'))


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'warlog.db')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_sent_flags_survive_a_restart(self):
        with Storage(self.path) as db:
            db.mark_sent('war1', 'preparation_msg', 'c1')
        with Storage(self.path) as db:
            self.assertTrue(db.is_sent('war1', 'preparation_msg', 'c1'))
            self.assertFalse(db.is_sent('war1', 'war_over_msg', 'c1'))
            self.assertFalse(db.is_sent('war2', 'preparation_msg', 'c1'))

    def test_archived_wars_round_trip(self):
        payload = {'state': 'warEnded', 'clan': {'name': 'ایران'}}
        with Storage(self.path) as db:
            db.archive_war('war1', payload)
            db.archive_war('war1', payload)  # replays must not duplicate
        with Storage(self.path) as db:
            self.assertEqual(list(db.archived_wars()), [('war1', payload)])

    def test_import_shelve_carries_sent_flags_over(self):
        old = os.path.join(self.tmpdir, 'old')
        with shelve.open(old) as legacy:
            legacy['war1'] = {'preparation_msg': True, 'war_msg': True}
            legacy['war2'] = {'preparation_msg': True}
        with Storage(self.path) as db:
            self.assertEqual(import_shelve(old, db, 'c1'), 3)
            self.assertTrue(db.is_sent('war1', 'war_msg', 'c1'))
            self.assertTrue(db.is_sent('war2', 'preparation_msg', 'c1'))


class LeagueWarCacheTestCase(unittest.TestCase):
    """Most of a league group is other clans' wars, fetched once."""

    def setUp(self):
        self.db = Storage(':memory:')
        self.fetched = []
        self.rounds = [{'warTags': ['#OURSDONE', '#THEIRSA']},
                       {'warTags': ['#OURSLIVE', '#THEIRSB']}]

    def _api(self):
        api = CoCAPI('token', cache=self.db)
        api._call_api = self._payload
        return api

    def _payload(self, endpoint):
        war_tag = '#' + endpoint.rsplit('%23', 1)[-1]
        self.fetched.append(war_tag)
        return {'state': 'inWar' if war_tag.endswith('LIVE') else 'warEnded',
                'teamSize': 15, 'preparationStartTime': 'T',
                'clan': {'tag': '#US' if war_tag.startswith('#OURS')
                                else '#OTHER' + war_tag,
                         'name': 'a', 'members': []},
                'opponent': {'tag': '#THEM' + war_tag, 'name': 'b',
                             'members': []}}

    def _populate(self):
        leagueinfo = LeagueInfo('#US', {'rounds': self.rounds})
        leagueinfo.populate_wartags(self._api())
        return leagueinfo

    def test_only_our_wars_are_kept(self):
        self.assertEqual(sorted(self._populate().our_wartags),
                         ['#OURSDONE', '#OURSLIVE'])

    def test_second_pass_only_refetches_unfinished_wars(self):
        self._populate()
        self.assertEqual(len(self.fetched), 4)
        self.fetched.clear()
        # A finished war cannot move, so it is read back from the warlog.
        # The live ones are still followed, including other clans', which
        # the standings need.
        self._populate()
        self.assertEqual(self.fetched, ['#OURSLIVE'])


class LeagueStandingsTestCase(unittest.TestCase):
    def _war(self, a, a_stars, b, b_stars, state='warEnded'):
        return WarInfo({'state': state, 'teamSize': 15,
                        'preparationStartTime': 'T',
                        'clan': {'tag': '#' + a, 'name': a, 'members': [],
                                 'stars': a_stars, 'destructionPercentage': 90},
                        'opponent': {'tag': '#' + b, 'name': b, 'members': [],
                                     'stars': b_stars,
                                     'destructionPercentage': 80}})

    def _standings(self, wars):
        leagueinfo = LeagueInfo('#A', {'rounds': []})
        leagueinfo.wartags.update(dict(enumerate(wars)))
        return LeagueStandings(leagueinfo).rows()

    def test_winner_takes_the_bonus_stars(self):
        rows = self._standings([self._war('A', 30, 'B', 25)])
        self.assertEqual([(r['name'], r['stars']) for r in rows],
                         [('A', 40), ('B', 25)])

    def test_a_draw_hands_out_no_bonus(self):
        # Equal stars and unequal destruction is a win, so force both equal.
        war = self._war('A', 30, 'B', 30)
        war.data['opponent']['destructionPercentage'] = 90
        rows = self._standings([war])
        self.assertEqual([r['stars'] for r in rows], [30, 30])

    def test_unfinished_wars_are_not_counted(self):
        self.assertEqual(
            self._standings([self._war('A', 30, 'B', 25, state='inWar')]), [])


class LeaguePlayerStatsTestCase(unittest.TestCase):
    def setUp(self):
        member = {'tag': '#P1', 'name': 'one', 'mapPosition': 1,
                  'townhallLevel': 15,
                  'attacks': [{'stars': 3, 'destructionPercentage': 100,
                               'order': 1, 'attackerTag': '#P1',
                               'defenderTag': '#X'}]}
        idle = {'tag': '#P2', 'name': 'two', 'mapPosition': 2,
                'townhallLevel': 14}
        self.warinfo = WarInfo({'state': 'warEnded', 'teamSize': 2,
                                'preparationStartTime': 'T',
                                'clan': {'tag': '#US', 'name': 'us',
                                         'members': [member, idle]},
                                'opponent': {'tag': '#THEM', 'name': 'them',
                                             'members': []}},
                               '#US', '#WAR1')
        self.leagueinfo = LeagueInfo('#US', {'rounds': []})
        self.leagueinfo.wartags['#WAR1'] = self.warinfo

    def test_counts_attacks_used_and_missed(self):
        rows = {row['name']: row for row in
                LeaguePlayerStats(self.leagueinfo).rows()}
        self.assertEqual((rows['one']['attacks'], rows['one']['missed'],
                          rows['one']['stars']), (1, 0, 3))
        self.assertEqual((rows['two']['attacks'], rows['two']['missed']),
                         (0, 1))

    def test_unused_attacks_lists_only_the_idle(self):
        self.assertEqual([m['name'] for m in unused_attacks(self.warinfo)],
                         ['two'])


class CommandBotTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Storage(':memory:')
        self.monitor = WarMonitor(self.db, MagicMock(), '#US', MagicMock(),
                                  ['c1'])
        self.monitor.warinfo = None
        self.monitor.leagueinfo = None
        registry.subscribe(self.db, '#US', 'c1')
        self.ctx = commands.Context(db=self.db,
                                    monitors={'#US': self.monitor})

    def answer(self, text, chat_id='c1', from_id=None):
        return [a.text for a in
                commands.answer(self.ctx, chat_id, from_id, text)]

    def test_unknown_command_is_not_silently_ignored(self):
        self.assertIn('/help', self.answer('/nope')[0])

    def test_commands_answer_without_a_war(self):
        for command in ('/war', '/missing', '/standings', '/stats'):
            self.assertTrue(self.answer(command)[0])

    def test_group_suffix_is_stripped(self):
        # Telegram sends /missing@thebot in groups.
        self.assertEqual(self.answer('/missing@clashogram'),
                         self.answer('/missing'))

    def test_idle_loop_does_not_spin(self):
        notifier = MagicMock()
        notifier.receive.return_value = []
        with patch('clashogram.runner.time.sleep') as sleep:
            deadline = [0, 5]
            with patch('clashogram.runner.time.monotonic',
                       side_effect=lambda: deadline.pop(0)):
                runner.answer_until(self.ctx, notifier, 3)
        sleep.assert_called_once()


class WarStatsTestCase(unittest.TestCase):
    def setUp(self):
        warinfo = WarInfo(load_wardata('warEnded_50.json'))
        self.stats = WarStats(warinfo)
        self.attack161 = {
            "destructionPercentage": 53,
            "attackerTag": "#9YUVL0CU",
            "order": 161,
            "stars": 2,
            "defenderTag": "#228U8G88L"
        }
        self.attack150 = {
            "destructionPercentage": 100,
            "attackerTag": "#2Q02GYCYV",
            "order": 150,
            "stars": 3,
            "defenderTag": "#2Y0C8YPYU"
        }

    def test_first_attack_stats(self):
        stats = self.stats.calculate_war_stats_sofar(1)

        self.assertEqual(stats['clan_destruction'], 0)
        self.assertEqual(stats['op_destruction'], 1.76)
        self.assertEqual(stats['clan_stars'], 0)
        self.assertEqual(stats['op_stars'], 2)
        self.assertEqual(stats['clan_used_attacks'], 0)
        self.assertEqual(stats['op_used_attacks'], 1)

    def test_42th_attack_stats(self):
        stats = self.stats.calculate_war_stats_sofar(42)

        self.assertEqual(stats['clan_destruction'], 44.16)
        self.assertEqual(stats['op_destruction'], 26.56)
        self.assertEqual(stats['clan_stars'], 61)
        self.assertEqual(stats['op_stars'], 37)
        self.assertEqual(stats['clan_used_attacks'], 27)
        self.assertEqual(stats['op_used_attacks'], 15)

    def test_last_attack_stats(self):
        stats = self.stats.calculate_war_stats_sofar(162)

        self.assertEqual(stats['clan_destruction'], 96.72)
        self.assertEqual(stats['op_destruction'], 98.90)
        self.assertEqual(stats['clan_stars'], 142)
        self.assertEqual(stats['op_stars'], 147)
        self.assertEqual(stats['clan_used_attacks'], 87)
        self.assertEqual(stats['op_used_attacks'], 75)

    def test_attack_destruction(self):
        self.assertEqual(
            self.stats.get_attack_new_destruction(self.attack161), 0)
        self.assertEqual(
            self.stats.get_attack_new_destruction(self.attack150), 3)

    def test_attack_new_stars(self):
        self.assertEqual(self.stats.get_attack_new_stars(self.attack161), 0)
        self.assertEqual(self.stats.get_attack_new_stars(self.attack150), 1)


class MessageFactoryTestCase(unittest.TestCase):
    def setUp(self):
        self.msg_factory = MessageFactory(None, None)
        self.setlocale_en()

    def _setlocale(self, language):
        os.environ['LANGUAGE'] = language
        gettext.bindtextdomain('messages',
                               localedir=os.path.join(os.curdir, 'locales'))
        gettext.textdomain('messages')

    def setlocale_en(self):
        self._setlocale('en_US.UTF-8')

    def setlocale_fa(self):
        self._setlocale('fa_IR.UTF-8')

    def test_format_time_default(self):
        os.environ['LANG'] = 'en'
        os.environ['LANGUAGE'] = 'en'
        timestr = self.msg_factory.format_time('20170603T191148.000Z')
        self.assertEqual(timestr, 'Sat, 03 Jun 2017 19:11:48')

    def test_format_time_fa(self):
        os.environ['LANG'] = 'fa'
        timestr = self.msg_factory.format_time('20170603T191148.000Z')
        self.assertEqual(timestr, 'شنبه، ۱۳ خرداد ۱۳۹۶ ۲۳:۴۱:۴۸')

    def test_format_time_fa_IR(self):
        os.environ['LANGUAGE'] = 'fa_IR'
        timestr = self.msg_factory.format_time('20170603T191148.000Z')
        self.assertEqual(timestr, 'شنبه، ۱۳ خرداد ۱۳۹۶ ۲۳:۴۱:۴۸')

    def test_format_time_fa_IR_locale(self):
        self.setlocale_fa()
        timestr = self.msg_factory.format_time('20170603T191148.000Z')
        self.assertEqual(timestr, 'شنبه، ۱۳ خرداد ۱۳۹۶ ۲۳:۴۱:۴۸')


class WarMonitorTestCase(unittest.TestCase):
    def setUp(self):
        coc_api = CoCAPI(None)
        self.warinfo = self.get_warinfo()
        our_claninfo = ClanInfo({'location': {'name': 'Iran',
                                              'isCountry': 'true',
                                              'countryCode': 'IR'},
                                 'warWinStreak': 0})
        coc_api.get_currentwar = MagicMock(return_value=self.warinfo)
        coc_api.get_claninfo = MagicMock(return_value=our_claninfo)
        notifier = TelegramNotifier(None)
        notifier.send = MagicMock()
        self.monitor = WarMonitor(Storage(':memory:'), coc_api, '', notifier,
                                  ['c1'])
        self.monitor.update()

        self.clan_attack = {
            "attackerTag": "#98VVJ8LV8",
            "defenderTag": "#8CCLRP2JC",
            "stars": 3,
            "destructionPercentage": 100,
            "order": 10
        }

    def get_warinfo(self):
        raise NotImplementedError()


class WarMonitorInWarTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'inWar_40.json'),
                 'r', encoding='utf8').read()))

    def test_send_preparation_msg(self):
        self.monitor.send_preparation_msg()

        self.assertTrue(self.monitor.is_msg_sent('preparation_msg', 'c1'))
        self.assertTrue(self.monitor.is_msg_sent('players_msg', 'c1'))

    def test_send_war_msg(self):
        self.monitor.send_war_msg()

        self.assertTrue(self.monitor.is_msg_sent('war_msg', 'c1'))

    def test_is_attack_msg_sent(self):
        self.assertTrue(self.monitor.is_msg_sent(
            self.monitor.get_attack_id(self.clan_attack), 'c1'))

    def test_get_attack_id(self):
        self.assertEqual(self.monitor.get_attack_id(self.clan_attack),
                         'attack98VVJ8LV88CCLRP2JC')

    def test_is_war_over_msg_sent(self):
        self.assertFalse(self.monitor.is_msg_sent('war_over_msg', 'c1'))

    def test_mark_msg_as_sent(self):
        self.monitor.mark_msg_as_sent('my_msg', 'c1')

        self.assertTrue(self.monitor.is_msg_sent('my_msg', 'c1'))
        self.assertFalse(self.monitor.is_msg_sent('nonexistent_msg', 'c1'))

    def test_full_destruction_msg_sent(self):
        self.assertFalse(self.monitor.is_msg_sent('clan_full_destruction', 'c1'))

    def test_op_destruction_msg_sent(self):
        self.assertFalse(self.monitor.is_msg_sent('op_full_destruction', 'c1'))


class WarMonitorFullDestructionTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'full_destruction.json'),
                 'r', encoding='utf8').read()))

    def test_full_destruction_msg_sent(self):
        self.assertTrue(self.monitor.is_msg_sent('clan_full_destruction', 'c1'))


class WarMonitorOpFullDestructionTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'op_full_destruction.json'),
                 'r', encoding='utf8').read()))

    def test_op_full_destruction_msg_sent(self):
        self.assertTrue(self.monitor.is_msg_sent('op_full_destruction', 'c1'))


class WarMonitorOnWarOverTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'warEnded_50.json'),
                 'r', encoding='utf8').read()))

    def test_reset_on_ended_war(self):
        with self.assertRaises(ValueError):
            self.monitor.is_msg_sent('war_over_msg', 'c1')

    def test_is_war_over_msg_sent(self):
        self.monitor.warinfo = self.warinfo
        self.assertTrue(self.monitor.is_msg_sent('war_over_msg', 'c1'))



class TwoClansInOneWarTestCase(unittest.TestCase):
    def test_neither_clan_suppresses_the_other(self):
        # Both sides resolve a war to one id on purpose, so delivery has
        # to be counted per chat or the second clan is told it has
        # already posted what it never posted.
        db = Storage(':memory:')
        notifier = MagicMock()
        ours = WarMonitor(db, MagicMock(), '#US', notifier, ['chat_us'])
        theirs = WarMonitor(db, MagicMock(), '#THEM', notifier, ['chat_them'])
        for monitor in (ours, theirs):
            monitor.warinfo = MagicMock()
            monitor.warinfo.create_war_id.return_value = 'SHARED'
            monitor.send_once(lambda: 'war is on', msg_id='war_msg')
        self.assertEqual(
            sorted(call.args[1] for call in notifier.send.call_args_list),
            ['chat_them', 'chat_us'])

    def test_a_chat_added_midwar_is_not_read_the_war_so_far(self):
        db = Storage(':memory:')
        registry.subscribe(db, '#US', 'first')
        db.mark_sent('W1', 'war_msg', 'first')
        registry.subscribe(db, '#US', 'second', war_id='W1')
        self.assertTrue(db.is_sent('W1', 'war_msg', 'second'))
        self.assertFalse(db.is_sent('W1', 'attack_later', 'second'))


class OperatorTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Storage(':memory:')
        self.ctx = commands.Context(db=self.db, monitors={}, admin_id='42')

    def answer(self, text, from_id, chat_id='c1'):
        return commands.answer(self.ctx, chat_id, from_id, text)

    def test_operator_follows_and_unfollows(self):
        self.answer('/add #US', from_id='42')
        self.assertEqual(self.db.subscriptions(), [('#US', 'c1')])
        self.answer('/remove #US', from_id='42')
        self.assertEqual(self.db.subscriptions(), [])

    def test_anybody_else_changes_nothing(self):
        answers = self.answer('/add #US', from_id='7')
        self.assertEqual(self.db.subscriptions(), [])
        self.assertIn('Operators only', answers[0].text)

    def test_a_channel_post_is_never_the_operator(self):
        # Channel posts carry no author, so from_id is None there.
        self.answer('/add #US', from_id=None)
        self.assertEqual(self.db.subscriptions(), [])

    def test_operator_commands_are_offered_to_the_operator_alone(self):
        self.assertNotIn('/remove', self.answer('/help', '7')[0].text)
        self.assertIn('/remove', self.answer('/help', '42')[0].text)

    def test_telegram_start_button_is_answered(self):
        self.assertNotIn('Unknown', self.answer('/start', '7')[0].text)

    def test_an_unfollowed_chat_gets_no_war_data(self):
        self.assertIn('No clan followed', self.answer('/war', '7')[0].text)


class RequestTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Storage(':memory:')

    def _ctx(self, open_requests):
        return commands.Context(db=self.db, monitors={}, admin_id='42',
                                open_requests=open_requests)

    def test_a_closed_instance_records_nothing(self):
        commands.answer(self._ctx(False), 'c1', '7', '/request #US')
        self.assertEqual(self.db.pending_requests(), [])

    def test_an_open_instance_files_it_without_granting_it(self):
        commands.answer(self._ctx(True), 'c1', '7', '/request #US')
        self.assertEqual(len(self.db.pending_requests()), 1)
        self.assertEqual(self.db.subscriptions(), [])

    def test_approving_is_what_grants_it(self):
        ctx = self._ctx(True)
        commands.answer(ctx, 'c1', '7', '/request #US')
        request_id = self.db.pending_requests()[0]['id']
        commands.answer(ctx, 'admin', '42', f'/approve {request_id}')
        self.assertEqual(self.db.subscriptions(), [('#US', 'c1')])


class AddValidationTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Storage(':memory:')

    def _ctx(self, known):
        coc_api = MagicMock()
        if known:
            coc_api.get_claninfo.return_value = ClanInfo({'name': 'iran'})
        else:
            response = MagicMock()
            response.status_code = 404
            coc_api.get_claninfo.side_effect = requests.HTTPError(
                '404', response=response)
        return commands.Context(db=self.db, monitors={}, admin_id='42',
                                coc_api=coc_api)

    def test_an_unknown_tag_is_refused_rather_than_stored(self):
        commands.answer(self._ctx(False), 'c1', '42', '/add #NOPE')
        self.assertEqual(self.db.subscriptions(), [])

    def test_a_mention_is_never_part_of_an_argument(self):
        commands.answer(self._ctx(True), 'c1', '42', '/add #US@Clashogram')
        self.assertEqual(self.db.subscriptions(), [('#US', 'c1')])


class MembershipTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Storage(':memory:')
        self.ctx = commands.Context(db=self.db, monitors={}, admin_id='42')

    def test_joining_hands_the_operator_the_id(self):
        # The only way to learn a channel's id, since nobody can be
        # recognised as the operator inside one.
        answer = commands.handle(self.ctx, Membership(
            -100448, 'Clan Wars', 'channel', joined=True))[0]
        target, message = answer.chat_id, answer.text
        self.assertEqual(target, '42')
        self.assertIn('-100448', message)

    def test_being_removed_stops_the_posting(self):
        registry.subscribe(self.db, '#US', '-100448')
        commands.handle(self.ctx, Membership(
            -100448, 'Clan Wars', 'channel', joined=False))
        self.assertEqual(self.db.subscriptions(), [])


class ReceiveTestCase(unittest.TestCase):
    def _updates(self, *updates):
        notifier = TelegramNotifier('token')
        response = MagicMock()
        response.json.return_value = {'result': list(updates)}
        with patch('clashogram.notifiers.requests.get', return_value=response):
            return list(notifier.receive())

    def test_a_channel_post_is_a_command_without_an_author(self):
        event, = self._updates({'update_id': 1, 'channel_post': {
            'text': '/chatid', 'chat': {'id': -100448, 'type': 'channel'}}})
        self.assertEqual((event.chat_id, event.from_id), (-100448, None))

    def test_membership_carries_whether_the_bot_is_still_there(self):
        for status, joined in (('administrator', True), ('left', False)):
            event, = self._updates({'update_id': 1, 'my_chat_member': {
                'chat': {'id': -1, 'type': 'channel', 'title': 'x'},
                'new_chat_member': {'status': status}}})
            self.assertEqual(event.joined, joined)

    def test_chatter_is_not_an_event(self):
        self.assertEqual(self._updates({'update_id': 1, 'message': {
            'text': 'hello', 'chat': {'id': -987, 'type': 'group'}}}), [])


class ArchiveTestCase(unittest.TestCase):
    def _run_a_finished_war(self, archive):
        db = Storage(':memory:')
        coc_api = CoCAPI(None)
        coc_api.get_currentwar = MagicMock(
            return_value=WarInfo(load_wardata('warEnded_50.json')))
        coc_api.get_claninfo = MagicMock(return_value=ClanInfo(
            {'location': {'name': 'Iran', 'isCountry': 'true',
                          'countryCode': 'IR'}, 'warWinStreak': 0}))
        monitor = WarMonitor(db, coc_api, '', MagicMock(), ['c1'],
                             archive=archive)
        monitor.update()
        return list(db.archived_wars())

    def test_the_flag_decides_whether_wars_are_kept(self):
        self.assertEqual(self._run_a_finished_war(False), [])
        self.assertEqual(len(self._run_a_finished_war(True)), 1)


class SentMigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'warlog.db')
        db = sqlite3.connect(self.path)
        db.executescript("""
            CREATE TABLE sent (
                war_id TEXT NOT NULL, msg_id TEXT NOT NULL,
                PRIMARY KEY (war_id, msg_id));
            INSERT INTO sent VALUES ('W1', 'war_msg');
        """)
        db.commit()
        db.close()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_old_rows_go_to_the_bootstrap_chat(self):
        with Storage(self.path, bootstrap_chat_id='c1') as db:
            self.assertTrue(db.is_sent('W1', 'war_msg', 'c1'))

    def test_unattributable_rows_go_rather_than_silence_a_chat(self):
        with Storage(self.path) as db:
            self.assertEqual(db.sent_msg_ids('W1', 'c1'), [])


class CoOperatorTestCase(unittest.TestCase):
    def setUp(self):
        self.db = Storage(':memory:')
        self.ctx = commands.Context(db=self.db, monitors={}, admin_id='42')

    def answer(self, text, from_id):
        return commands.answer(self.ctx, 'c1', from_id, text)

    def test_owner_lets_somebody_help_and_stops_letting_them(self):
        self.answer('/addoperator 77', from_id='42')
        self.answer('/add #US', from_id='77')
        self.assertEqual(self.db.subscriptions(), [('#US', 'c1')])
        self.answer('/removeoperator 77', from_id='42')
        self.answer('/remove #US', from_id='77')
        self.assertEqual(self.db.subscriptions(), [('#US', 'c1')])

    def test_a_co_operator_cannot_unseat_the_owner(self):
        self.answer('/addoperator 77', from_id='42')
        self.answer('/removeoperator 42', from_id='77')
        self.answer('/addoperator 99', from_id='77')
        self.assertEqual(self.db.operators(), ['77'])


class NetworkBlipTestCase(unittest.TestCase):
    def test_a_dns_blip_does_not_kill_the_poll(self):
        # What crash-looped the deployed bot 28 times: ConnectionError is
        # not an HTTPError, so it fell through to a bare except that tried
        # to send a message, which failed the same way, and died.
        monitor = MagicMock()
        monitor.coc_api.get_currentleague.side_effect = \
            requests.ConnectionError('cannot resolve api.clashofclans.com')
        self.assertEqual(runner.poll(monitor, MagicMock()), runner.BACKOFF)

    def test_telegram_being_unreachable_does_not_kill_the_loop(self):
        notifier = MagicMock()
        notifier.receive.side_effect = requests.ConnectionError('no dns')
        ctx = commands.Context(db=Storage(':memory:'), monitors={})
        with patch('clashogram.runner.time.sleep') as sleep, \
             patch('clashogram.runner.time.monotonic',
                   side_effect=[0, 5]):
            runner.answer_until(ctx, notifier, 3)
        sleep.assert_called_once()


class HtmlSafetyTestCase(unittest.TestCase):
    def test_nothing_the_bot_says_looks_like_markup(self):
        # Replies go out with parse_mode=HTML, so a literal <clan tag>
        # is a 400 and the answer is lost. reply() used to swallow it.
        ctx = commands.Context(db=Storage(':memory:'), monitors={},
                               admin_id='42')
        for command in ('/chatid', '/start', '/help', '/add', '/remove',
                        '/approve', '/request', '/addoperator',
                        '/removeoperator', '/clans', '/operators'):
            for answer in commands.answer(ctx, -1, 42, command):
                self.assertNotIn('<', answer.text, command)

    def test_a_clan_named_with_a_bracket_is_escaped(self):
        coc_api = MagicMock()
        coc_api.get_claninfo.return_value = ClanInfo({'name': 'a<b'})
        db = Storage(':memory:')
        ctx = commands.Context(db=db, monitors={}, admin_id='42',
                               coc_api=coc_api)
        message = commands.answer(ctx, 'c1', '42', '/add #US')[0].text
        self.assertIn('a&lt;b', message)


class AnswerShapeTestCase(unittest.TestCase):
    def test_every_command_answers_with_answers(self):
        # The runner reads .chat_id off each one. A bare tuple raises
        # AttributeError there, which is not a network error, so it
        # escapes the loop and takes the process with it.
        db = Storage(':memory:')
        coc = MagicMock()
        coc.get_claninfo.return_value = ClanInfo({'name': 'iran'})
        ctx = commands.Context(db=db, monitors={}, admin_id='42',
                               coc_api=coc, open_requests=True)
        commands.answer(ctx, 'g1', 7, '/request #US')
        for command in ('/addoperator 77', '/removeoperator 77', '/operators',
                        '/clans', '/add #US', '/remove #US', '/requests',
                        '/requests open', '/requests close', '/approve 1',
                        '/deny 1', '/request #US', '/help', '/start',
                        '/chatid', '/war', '/nope'):
            for answer in commands.answer(ctx, 'g1', 42, command, 'group',
                                          'mehdi'):
                self.assertIsInstance(answer, commands.Answer, command)


class PerChatDeliveryTestCase(unittest.TestCase):
    def _monitor(self, db, chats):
        monitor = WarMonitor(db, MagicMock(), '#US', MagicMock(), chats)
        monitor.warinfo = MagicMock()
        monitor.warinfo.create_war_id.return_value = 'W1'
        return monitor

    def test_each_chat_is_told_in_its_own_language(self):
        db = Storage(':memory:')
        db.set_chat_lang('fa', 'fa_IR')
        db.set_chat_lang('en', 'en')
        monitor = self._monitor(db, ['fa', 'en'])
        monitor.send_once(lambda: gettext_('Not in a war.'), 'm', kind='result')
        said = {c.args[1]: c.args[0] for c in monitor.notifier.send.call_args_list}
        self.assertEqual(said['en'], 'Not in a war.')
        self.assertNotEqual(said['fa'], said['en'])

    def test_a_muted_kind_is_skipped_but_not_replayed_later(self):
        db = Storage(':memory:')
        db.set_muted_kinds('quiet', {'attacks'})
        monitor = self._monitor(db, ['quiet', 'loud'])
        monitor.send_once(lambda: 'boom', 'a1', kind='attacks')
        self.assertEqual([c.args[1] for c in monitor.notifier.send.call_args_list],
                         ['loud'])
        self.assertTrue(db.is_sent('W1', 'a1', 'quiet'))


class ChatColumnsTestCase(unittest.TestCase):
    def test_a_chat_table_from_before_gains_the_new_columns(self):
        # This crash-looped the deployed bot: the table already existed,
        # so CREATE TABLE IF NOT EXISTS never added lang, muted or
        # steward, and every command died on the first lookup.
        tmpdir = tempfile.mkdtemp()
        try:
            path = os.path.join(tmpdir, 'old.db')
            old = sqlite3.connect(path)
            old.executescript("""
                CREATE TABLE chat (chat_id TEXT PRIMARY KEY,
                                   title TEXT NOT NULL);
                INSERT INTO chat VALUES ('c1', 'Clan Chat');
            """)
            old.commit()
            old.close()
            with Storage(path) as db:
                self.assertIsNone(db.chat_lang('c1'))
                self.assertEqual(db.muted_kinds('c1'), set())
                self.assertIsNone(db.chat_steward('c1'))
                db.set_chat_lang('c1', 'fa_IR')
                self.assertEqual(db.chat_lang('c1'), 'fa_IR')
                self.assertEqual(db.chat_titles(), {'c1': 'Clan Chat'})
        finally:
            shutil.rmtree(tmpdir)


class EscapingTestCase(unittest.TestCase):
    EVIL = '<b>x</b>'

    def _ctx(self, db, known=True):
        coc = MagicMock()
        if known:
            coc.get_claninfo.return_value = ClanInfo({'name': self.EVIL})
        else:
            response = MagicMock()
            response.status_code = 404
            coc.get_claninfo.side_effect = requests.HTTPError(
                '404', response=response)
        return commands.Context(db=db, monitors={}, admin_id='42',
                                coc_api=coc, open_requests=True)

    def test_nothing_somebody_typed_comes_back_as_markup(self):
        # Replies go out with parse_mode=HTML, so an unescaped echo lets
        # anyone put their own markup, or a link, in the bot's voice.
        db = Storage(':memory:')
        for command in (f'/add {self.EVIL}', f'/remove {self.EVIL}',
                        f'/removeoperator {self.EVIL}'):
            said = commands.answer(self._ctx(db, known=False), 'c1', '42',
                                   command)[0].text
            self.assertNotIn('<b>', said, command)

    def test_a_telegram_first_name_cannot_reach_the_operator_as_markup(self):
        db = Storage(':memory:')
        answers = commands.answer(self._ctx(db), 'g1', 7, '/request #US',
                                  'group', self.EVIL)
        told = [a.text for a in answers if a.chat_id == '42'][0]
        self.assertNotIn('<b>', told)

    def test_a_clan_named_with_markup_is_escaped(self):
        db = Storage(':memory:')
        said = commands.answer(self._ctx(db), 'c1', '42', '/add #US')[0].text
        self.assertNotIn('<b>', said)


if __name__ == '__main__':
    unittest.main()
