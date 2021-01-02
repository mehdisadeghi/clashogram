########################################################################
# Helper functions
########################################################################
import os
import json


def save_wardata(wardata):
    if wardata['state'] != 'notInWar':
        war_id = "{0}{1}".format(wardata['clan']['tag'][1:],
                                 wardata['preparationStartTime'])
        if not os.path.exists('warlog'):
            os.mkdir('warlog')
        path = os.path.join('warlog', war_id)
        json.dump(wardata,
                  open(path, 'w', encoding='utf-8'), ensure_ascii=False)


def save_latest_data(wardata, monitor):
    if wardata:
        save_wardata(wardata)
        json.dump(wardata,
                  open('latest_downloaded_wardata.json',
                       'w',
                       encoding='utf-8'),
                  ensure_ascii=False)


########################################################################
# DB helper classes (mainly to faciliate serveress)
########################################################################

class SimpleKVDB(object):
    def __init__(self, db):
        self._db = db

    def __contains__(self, key):
        return key in self._db

    def __getitem__(self, key):
        return self._db[key]

    def __setitem__(self, key, value):
        self._db[key] = value
        self._db.sync()
