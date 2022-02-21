########################################################################
# CoC API Calls
########################################################################
import requests
import json

from .models import WarInfo, ClanInfo, LeagueInfo


class CoCAPI(object):
    def __init__(self, coc_token):
        self.coc_token = coc_token

    def get_currentwar(self, clan_tag, war_tag=None):
        return WarInfo(
            self._call_api(self._get_currentwar_endpoint(clan_tag, war_tag)))

    def get_claninfo(self, clan_tag):
        return ClanInfo(self._call_api(self._get_claninfo_endpoint(clan_tag)))

    def get_currentleague(self, clan_tag, populate_wartags=True):
        league_info = None
        try:
            league_info = LeagueInfo(
                clan_tag,
                self._call_api(self._get_currentleague_endpoint(clan_tag)))
            if populate_wartags:
                league_info.populate_wartags(self)
        except Exception as err:
            # Server returns 404 if the clan does not participate in league war
            if '404' not in str(err):
                raise err
        return league_info

    def _call_api(self, endpoint):
        res = requests.get(endpoint,
                    headers={'Authorization': f'Bearer {self.coc_token}'})
        if res.status_code == requests.codes.ok:
            return json.loads(res.content.decode('utf-8'))
        else:
            raise res.raise_for_status()

    def _get_currentwar_endpoint(self, clan_tag, war_tag):
        if war_tag:
            return 'https://api.clashofclans.com/v1/clanwarleagues/wars/{war_tag}'\
                .format(war_tag=requests.utils.quote(war_tag))
        else:
            return 'https://api.clashofclans.com/v1/clans/{clan_tag}/currentwar'\
                .format(clan_tag=requests.utils.quote(clan_tag))

    def _get_claninfo_endpoint(self, clan_tag):
        return 'https://api.clashofclans.com/v1/clans/{clan_tag}'.format(
            clan_tag=requests.utils.quote(clan_tag))

    def _get_currentleague_endpoint(self, clan_tag):
        return 'https://api.clashofclans.com/v1/clans/{clan_tag}/currentwar/leaguegroup'.format(
            clan_tag=requests.utils.quote(clan_tag))
