########################################################################
# Models according to CoC API
########################################################################

class ClanInfo(object):
    def __init__(self, clandata):
        self.data = clandata

    @property
    def location(self):
        return self.data.get('location', {}).get('name', '')

    @property
    def country_flag_imoji(self):
        if 'location' not in self.data:
            return ''

        if self.data['location']['isCountry']:
            return self._get_country_flag_imoji(
                self.data['location']['countryCode'])
        elif self.data['location']['name'] == 'International':
            # The unicode character for planet earth, not empty string!
            return '🌎'
        else:
            return ''

    def _get_country_flag_imoji(self, country_code):
        return "{}{}".format(chr(127397 + ord(country_code[0])),
                             chr(127397 + ord(country_code[1])))

    @property
    def winstreak(self):
        return self.data['warWinStreak']

    @property
    def is_warlog_public(self):
        return self.data['isWarLogPublic']


class WarInfo(object):
    def __init__(self, wardata):
        self.data = wardata
        self.clan_members = {}
        self.opponent_members = {}
        self.players = {}
        self.ordered_attacks = None
        self._populate()

    @property
    def state(self):
        return self.data['state']

    @property
    def clan_tag(self):
        return self.data['clan']['tag']

    @property
    def op_tag(self):
        return self.data['opponent']['tag']

    @property
    def clan_name(self):
        return self.data['clan']['name']

    @property
    def op_name(self):
        return self.data['opponent']['name']

    @property
    def clan_level(self):
        return self.data['clan']['clanLevel']

    @property
    def op_level(self):
        return self.data['opponent']['clanLevel']

    @property
    def clan_destruction(self):
        return self.data['clan']['destructionPercentage']

    @property
    def op_destruction(self):
        return self.data['opponent']['destructionPercentage']

    @property
    def clan_stars(self):
        return self.data['clan']['stars']

    @property
    def op_stars(self):
        return self.data['opponent']['stars']

    @property
    def clan_attacks(self):
        return self.data['clan']['attacks']

    @property
    def op_attacks(self):
        return self.data['opponent']['attacks']

    @property
    def start_time(self):
        return self.data['startTime']

    @property
    def team_size(self):
        return self.data['teamSize']

    def _populate(self):
        if self.is_not_in_war():
            return
        for member in self.data['clan']['members']:
            self.clan_members[member['tag']] = member
            self.players[member['tag']] = member
        for opponent in self.data['opponent']['members']:
            self.opponent_members[opponent['tag']] = opponent
            self.players[opponent['tag']] = opponent
        self.ordered_attacks = self.get_ordered_attacks()

    def get_ordered_attacks(self):
        ordered_attacks = {}
        for player in self.players.values():
            for attack in self.get_player_attacks(player):
                ordered_attacks[attack['order']] = (player, attack)
        return ordered_attacks

    def get_player_attacks(self, player):
        if 'attacks' in player:
            return player['attacks']
        else:
            return []

    def get_player_info(self, tag):
        if tag not in self.players:
            raise Exception('Player %s not found.' % tag)
        return self.players[tag]

    def is_not_in_war(self):
        return self.data['state'] == 'notInWar'

    def is_in_preparation(self):
        return self.data['state'] == 'preparation'

    def is_in_war(self):
        return self.data['state'] == 'inWar'

    def is_war_over(self):
        return self.data['state'] == 'warEnded'

    def is_clan_member(self, player):
        return player['tag'] in self.clan_members

    def is_win(self):
        if self.data['clan']['stars'] > self.data['opponent']['stars']:
            return True
        elif self.data['clan']['stars'] == self.data['opponent']['stars'] and\
                (self.data['clan']['destructionPercentage'] > self.data['opponent']['destructionPercentage']):
            return True
        else:
            return False

    def is_draw(self):
        return \
            self.data['clan']['stars'] == self.data['opponent']['stars'] and\
            (self.data['clan']['destructionPercentage'] == self.data['opponent']['destructionPercentage'])

    def create_war_id(self):
        return "{0}{1}{2}".format(self.data['clan']['tag'],
                                  self.data['opponent']['tag'],
                                  self.data['preparationStartTime'])


class LeagueInfo(object):
    """
    {
      "tag": "string",
      "state": "string",
      "season": "string",
      "clans": [
        {
          "tag": "string",
          "clanLevel": 0,
          "name": "string",
          "members": [
            {
              "tag": "string",
              "townHallLevel": 0,
              "name": "string"
            }
          ],
          "badgeUrls": {}
        }
      ],
      "rounds": [
        {
          "warTags": [
            "string"
          ]
        }
      ]
    }
    """
    def __init__(self, clan_tag, data):
        self.clan_tag = clan_tag
        self.data = data

        self._wartags = {}

    @property
    def state(self):
        return self.data['state']

    @property
    def season(self):
        return self.data['season']

    @property
    def clans(self):
        return self.data['clans']

    @property
    def rounds(self):
        return self.data['rounds']

    @property
    def our_wartags(self):
        return {wartag: warinfo for wartag, warinfo in self._wartags.items() if warinfo.clan_tag == self.clan_tag}

    @property
    def wartags(self):
        return self._wartags

    def populate_wartags(self, api):
        for rnd in self.rounds:
            for war_tag in rnd['warTags']:
                if war_tag == '#0':
                    continue
                self._wartags[war_tag] = api.get_currentwar(None, war_tag)

    def reset(self):
        self._wartags.clear()

    def get_previous_wartags(self):
        for wartag, warinfo in self.our_wartags.items():
            if warinfo.is_war_over():
                yield wartag

    def get_current_wartag(self):
        # Simply return the first tag which is either in preparation or inWar.
        for wartag, warinfo in self.our_wartags.items():
            if warinfo.is_in_war():
                return wartag

    def get_next_wartag(self):
        for wartag, warinfo in self.our_wartags.items():
            if warinfo.is_in_preparation():
                return wartag

    def is_not_in_war(self):
        return self.data['state'] == 'notInWar'

    def is_in_preparation(self):
        return self.data['state'] == 'preparation'

    def is_in_war(self):
        return self.data['state'] == 'inWar'

    def is_war_over(self):
        return self.data['state'] == 'warEnded'

    def is_win(self):
        if self.data['clan']['stars'] > self.data['opponent']['stars']:
            return True
        elif self.data['clan']['stars'] == self.data['opponent']['stars'] and\
                (self.data['clan']['destructionPercentage'] > self.data['opponent']['destructionPercentage']):
            return True
        else:
            return False

    def create_war_id(self):
        return "{0}{1}{2}".format(self.data['season'],
                                  len(self.data['clans']),
                                  len(self.data['rounds']))


########################################################################
# War statistics
########################################################################

class WarStats(object):
    def __init__(self, warinfo):
        self.warinfo = warinfo

    def calculate_war_stats_sofar(self, attack_order):
        """Calculate latest war stats.

        CoC data is updated every 10 minutes and reflects stats after the
        last attack. We have to calculate the necesssary info for the
        previous ones"""
        info = {}
        info['clan_destruction'] = 0
        info['op_destruction'] = 0
        info['clan_stars'] = 0
        info['op_stars'] = 0
        info['clan_used_attacks'] = 0
        info['op_used_attacks'] = 0
        for order in range(1, attack_order + 1):
            player, attack = self.warinfo.ordered_attacks[order]
            if self.warinfo.is_clan_member(player):
                info['clan_destruction'] +=\
                    self.get_attack_new_destruction(attack)
                info['clan_stars'] += self.get_attack_new_stars(attack)
                info['clan_used_attacks'] += 1
            else:
                info['op_destruction'] +=\
                    self.get_attack_new_destruction(attack)
                info['op_stars'] += self.get_attack_new_stars(attack)
                info['op_used_attacks'] += 1
        info['op_destruction'] /= self.warinfo.team_size
        info['clan_destruction'] /= self.warinfo.team_size
        return info

    def get_latest_war_stats(self):
        return {'clan_destruction': self.warinfo.clan_destruction,
                'op_destruction': self.warinfo.op_destruction,
                'clan_stars': self.warinfo.clan_stars,
                'op_stars': self.warinfo.op_stars,
                'clan_used_attacks': self.warinfo.clan_attacks,
                'op_used_attacks': self.warinfo.op_attacks}

    def get_attack_new_destruction(self, attack):
        if (attack['destructionPercentage'] > self.get_best_attack_destruction_upto(attack)):
            return (attack['destructionPercentage'] - self.get_best_attack_destruction_upto(attack))
        else:
            return 0

    def get_best_attack_destruction(self, attack):
        defender = self.warinfo.get_player_info(attack['defenderTag'])
        if 'bestOpponentAttack' in defender and\
                (defender['bestOpponentAttack']['attackerTag'] != attack['attackerTag']):
            return defender['bestOpponentAttack']['destructionPercentage']
        else:
            return 0

    def get_best_attack_destruction_upto(self, in_attack):
        best_score = 0
        for order in range(1, in_attack['order'] + 1):
            player, attack = self.warinfo.ordered_attacks[order]
            if attack['defenderTag'] == in_attack['defenderTag'] and\
               attack['destructionPercentage'] > best_score and\
               attack['attackerTag'] != in_attack['attackerTag']:
                best_score = attack['destructionPercentage']
        return best_score

    def get_attack_new_stars(self, attack):
        existing_stars = self.get_best_attack_stars_upto(attack)
        stars = attack['stars'] - existing_stars
        if stars > 0:
            return stars
        else:
            return 0

    def get_best_attack_stars_upto(self, in_attack):
        best_score = 0
        for order in range(1, in_attack['order'] + 1):
            player, attack = self.warinfo.ordered_attacks[order]
            if attack['defenderTag'] == in_attack['defenderTag'] and\
               attack['stars'] > best_score and\
               attack['attackerTag'] != in_attack['attackerTag']:
                best_score = attack['stars']
        return best_score
