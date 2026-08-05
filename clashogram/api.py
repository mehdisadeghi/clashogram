########################################################################
# CoC API Calls
########################################################################
import json
import time

import requests

from .models import (
    ClanCapital,
    ClanInfo,
    LeagueInfo,
    PlayerInfo,
    WarInfo,
    WarLog,
)

BASE_URL = 'https://api.clashofclans.com/v1'
RETRIES = 3
RETRY_AFTER = 5


class CoCAPI:
    def __init__(self, coc_token, cache=None):
        self.coc_token = coc_token
        self.cache = cache

    def get_currentwar(self, clan_tag, war_tag=None):
        return WarInfo(
            self._call_api(self._get_currentwar_endpoint(clan_tag, war_tag)),
            clan_tag, war_tag)

    def get_league_war(self, war_tag, clan_tag):
        """Fetch one war of a league group.

        Every war in the group is followed, not only ours, because the
        standings need all eight clans. A finished war cannot move, so
        once it has ended it is read from the warlog and never asked
        for again."""
        payload = self.cache and self.cache.finished_war(war_tag)
        if payload is None:
            payload = self._call_api(
                self._get_currentwar_endpoint(None, war_tag))
            if self.cache:
                self.cache.remember_war(
                    war_tag, payload, payload['state'] == 'warEnded')
        return WarInfo(payload, clan_tag, war_tag)

    def get_claninfo(self, clan_tag):
        return ClanInfo(self._call_api(self._get_claninfo_endpoint(clan_tag)))

    def get_warlog(self, clan_tag):
        return WarLog(self._call_api(self._clan_endpoint(clan_tag, 'warlog')))

    def get_capitalraidseasons(self, clan_tag):
        return ClanCapital(
            self._call_api(self._clan_endpoint(clan_tag, 'capitalraidseasons')))

    def get_playerinfo(self, player_tag):
        return PlayerInfo(self._call_api(
            f'{BASE_URL}/players/{requests.utils.quote(player_tag)}'))

    def get_warleagues(self):
        return self._call_api(f'{BASE_URL}/warleagues')['items']

    def get_leaguetiers(self):
        # /leaguetiers replaced /leagues in the ranked league rework.
        return self._call_api(f'{BASE_URL}/leaguetiers')['items']

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
                

    def _clan_endpoint(self, clan_tag, resource):
        return (f'{BASE_URL}/clans/{requests.utils.quote(clan_tag)}'
                f'/{resource}')

    def _get_claninfo_endpoint(self, clan_tag):
        return f'https://api.clashofclans.com/v1/clans/{requests.utils.quote(clan_tag)}'

    def _get_currentleague_endpoint(self, clan_tag):
        return f'https://api.clashofclans.com/v1/clans/{requests.utils.quote(clan_tag)}/currentwar/leaguegroup'
