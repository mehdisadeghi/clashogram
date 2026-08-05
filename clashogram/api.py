########################################################################
# CoC API Calls
########################################################################
import json
import time

import requests

from .models import ClanInfo, LeagueInfo, WarInfo

RETRIES = 3
RETRY_AFTER = 5


class CoCAPI:
    def __init__(self, coc_token):
        self.coc_token = coc_token

    def get_currentwar(self, clan_tag, war_tag=None):
        return WarInfo(
            self._call_api(self._get_currentwar_endpoint(clan_tag, war_tag)),
            clan_tag, war_tag)

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
                raise
        return league_info

    def _call_api(self, endpoint):
        for _ in range(RETRIES):
            res = requests.get(endpoint,
                    headers={'Authorization': f'Bearer {self.coc_token}'})
            if res.status_code != requests.codes.too_many_requests:
                break
            time.sleep(self._retry_after(res))
        res.raise_for_status()
        return json.loads(res.content.decode('utf-8'))

    def _retry_after(self, res):
        return int(res.headers.get('Retry-After', RETRY_AFTER))

    def _get_currentwar_endpoint(self, clan_tag, war_tag):
        if war_tag:
            return f'https://api.clashofclans.com/v1/clanwarleagues/wars/{requests.utils.quote(war_tag)}'\
                
        else:
            return f'https://api.clashofclans.com/v1/clans/{requests.utils.quote(clan_tag)}/currentwar'\
                

    def _get_claninfo_endpoint(self, clan_tag):
        return f'https://api.clashofclans.com/v1/clans/{requests.utils.quote(clan_tag)}'

    def _get_currentleague_endpoint(self, clan_tag):
        return f'https://api.clashofclans.com/v1/clans/{requests.utils.quote(clan_tag)}/currentwar/leaguegroup'
