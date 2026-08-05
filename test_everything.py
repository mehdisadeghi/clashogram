'''Clashogram tests.'''
import gettext
import json
import os
import shelve
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from clashogram.__main__ import WarMonitor
from clashogram.api import CoCAPI
from clashogram.formatters import MessageFactory
from clashogram.models import (
    ClanInfo,
    LeagueInfo,
    LeagueStandings,
    WarInfo,
    WarStats,
)
from clashogram.notifiers import TelegramNotifier
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
        notifier = TelegramNotifier('token', 'chat')
        with patch('clashogram.notifiers.requests.post') as post, \
             patch('clashogram.notifiers.time.sleep') as sleep:
            post.side_effect = [
                self._response(429, {'parameters': {'retry_after': 7}}),
                self._response(200)]
            notifier.send('hi')
            self.assertEqual(post.call_count, 2)
            sleep.assert_called_once_with(7)

    def test_undelivered_message_is_not_marked_sent(self):
        monitor = WarMonitor(Storage(':memory:'), MagicMock(), '#TAG',
                             MagicMock())
        monitor.warinfo = MagicMock()
        monitor.warinfo.create_war_id.return_value = 'W1'
        monitor.notifier.send.side_effect = requests.HTTPError('429')
        with self.assertRaises(requests.HTTPError):
            monitor.send_once('hi', msg_id='m1')
        self.assertFalse(monitor.is_msg_sent('m1'))


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, 'warlog.db')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_sent_flags_survive_a_restart(self):
        with Storage(self.path) as db:
            db.mark_sent('war1', 'preparation_msg')
        with Storage(self.path) as db:
            self.assertTrue(db.is_sent('war1', 'preparation_msg'))
            self.assertFalse(db.is_sent('war1', 'war_over_msg'))
            self.assertFalse(db.is_sent('war2', 'preparation_msg'))

    def test_import_shelve_carries_sent_flags_over(self):
        old = os.path.join(self.tmpdir, 'old')
        with shelve.open(old) as legacy:
            legacy['war1'] = {'preparation_msg': True, 'war_msg': True}
            legacy['war2'] = {'preparation_msg': True}
        with Storage(self.path) as db:
            self.assertEqual(import_shelve(old, db), 3)
            self.assertTrue(db.is_sent('war1', 'war_msg'))
            self.assertTrue(db.is_sent('war2', 'preparation_msg'))


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
        notifier = TelegramNotifier(None, None)
        notifier.send = MagicMock()
        self.monitor = WarMonitor(Storage(':memory:'), coc_api, '', notifier)
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

        self.assertTrue(self.monitor.is_msg_sent('preparation_msg'))
        self.assertTrue(self.monitor.is_msg_sent('players_msg'))

    def test_send_war_msg(self):
        self.monitor.send_war_msg()

        self.assertTrue(self.monitor.is_msg_sent('war_msg'))

    def test_is_attack_msg_sent(self):
        self.assertTrue(self.monitor.is_msg_sent(
            self.monitor.get_attack_id(self.clan_attack)))

    def test_get_attack_id(self):
        self.assertEqual(self.monitor.get_attack_id(self.clan_attack),
                         'attack98VVJ8LV88CCLRP2JC')

    def test_is_war_over_msg_sent(self):
        self.assertFalse(self.monitor.is_msg_sent('war_over_msg'))

    def test_mark_msg_as_sent(self):
        self.monitor.mark_msg_as_sent('my_msg')

        self.assertTrue(self.monitor.is_msg_sent('my_msg'))
        self.assertFalse(self.monitor.is_msg_sent('nonexistent_msg'))

    def test_full_destruction_msg_sent(self):
        self.assertFalse(self.monitor.is_msg_sent('clan_full_destruction'))

    def test_op_destruction_msg_sent(self):
        self.assertFalse(self.monitor.is_msg_sent('op_full_destruction'))


class WarMonitorFullDestructionTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'full_destruction.json'),
                 'r', encoding='utf8').read()))

    def test_full_destruction_msg_sent(self):
        self.assertTrue(self.monitor.is_msg_sent('clan_full_destruction'))


class WarMonitorOpFullDestructionTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'op_full_destruction.json'),
                 'r', encoding='utf8').read()))

    def test_op_full_destruction_msg_sent(self):
        self.assertTrue(self.monitor.is_msg_sent('op_full_destruction'))


class WarMonitorOnWarOverTestCase(WarMonitorTestCase):
    def get_warinfo(self):
        return WarInfo(json.loads(
            open(os.path.join('data', 'warEnded_50.json'),
                 'r', encoding='utf8').read()))

    def test_reset_on_ended_war(self):
        with self.assertRaises(ValueError):
            self.monitor.is_msg_sent('war_over_msg')

    def test_is_war_over_msg_sent(self):
        self.monitor.warinfo = self.warinfo
        self.assertTrue(self.monitor.is_msg_sent('war_over_msg'))


if __name__ == '__main__':
    unittest.main()
