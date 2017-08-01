'''Clashogram tests.'''
import os
import unittest
from unittest.mock import MagicMock
import json
from clashogram import CoCAPI, ClanInfo, WarInfo, WarStats, MessageFactory, WarMonitor, TelegramNotifier


class ClanInfoTestCase(unittest.TestCase):
    def setUp(self):
        self.claninfo = ClanInfo({'location': {'name': 'Iran',
                                               'isCountry': 'true',
                                               'countryCode': 'IR'},
                                  'warWinStreak': 0})

    def test_location(self):
        assert self.claninfo.get_location() == 'Iran'

    def test_country_imoji(self):
        assert self.claninfo.get_country_flag_imoji() ==  '🇮🇷'

    def test_winstreak(self):
        assert self.claninfo.get_winstreak() == 0


class WarInfoTestCase(unittest.TestCase):
    def setUp(self):
        self.warinfo = WarInfo(json.loads(open(os.path.join('data', 'inWar_40.json'), 'r', encoding='utf8').read()))
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
        self.assertRaises(Exception, '#2GCZZZZP8')

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
        self.assertEqual(self.warinfo.create_war_id(), "#YVL0C8UY#JC0L922Y20170602T201148.000Z")


class WarStatsTestCase(unittest.TestCase):
    def setUp(self):
        warinfo = WarInfo(json.loads(open(os.path.join('data', 'warEnded_50.json'), 'r', encoding='utf8').read()))
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
        self.assertEqual(self.stats.get_attack_new_destruction(self.attack161), 0)
        self.assertEqual(self.stats.get_attack_new_destruction(self.attack150), 3)

    def test_attack_new_stars(self):
        self.assertEqual(self.stats.get_attack_new_stars(self.attack161), 0)
        self.assertEqual(self.stats.get_attack_new_stars(self.attack150), 1)


class MessageFactoryTestCase(unittest.TestCase):
    pass


class WarMonitorTestCase(unittest.TestCase):
    def setUp(self):
        coc_api = CoCAPI(None)
        self.warinfo = WarInfo(json.loads(open(os.path.join('data', 'inWar_40.json'), 'r', encoding='utf8').read()))
        our_claninfo = ClanInfo({'location': {'name': 'Iran',
                                              'isCountry': 'true',
                                              'countryCode': 'IR'},
                                 'warWinStreak': 0})
        coc_api.get_currentwar = MagicMock(return_value=self.warinfo)
        coc_api.get_claninfo = MagicMock(return_value=our_claninfo)
        notifier = TelegramNotifier(None, None)
        notifier.send = MagicMock()
        self.monitor = WarMonitor({}, coc_api, notifier)
        self.monitor.update(self.warinfo)

        self.clan_attack = {
            "attackerTag": "#98VVJ8LV8",
            "defenderTag": "#8CCLRP2JC",
            "stars": 3,
            "destructionPercentage": 100,
            "order": 10
        }

    def test_send_preparation_msg(self):
        self.monitor.send_preparation_msg()

        self.assertTrue(self.monitor.is_preparation_msg_sent())

    def test_send_war_msg(self):
        self.monitor.send_war_msg()

        self.assertTrue(self.monitor.is_war_msg_sent())

    def test_is_attack_msg_sent(self):
        self.assertTrue(self.monitor.is_attack_msg_sent(self.clan_attack))

    def test_get_attack_id(self):
        self.assertEqual(self.monitor.get_attack_id(self.clan_attack), 'attack98VVJ8LV88CCLRP2JC')

    def test_is_war_over_msg_sent(self):
        self.assertFalse(self.monitor.is_war_over_msg_sent(self.warinfo))



if __name__ == '__main__':
    unittest.main()