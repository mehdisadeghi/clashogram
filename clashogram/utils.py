########################################################################
# Helper functions
########################################################################
import json
import os


def save_wardata(wardata):
    if wardata['state'] != 'notInWar':
        war_id = "{}{}".format(wardata['clan']['tag'][1:],
                                 wardata['preparationStartTime'])
        if not os.path.exists('warlog'):
            os.mkdir('warlog')
        path = os.path.join('warlog', war_id)
        with open(path, 'w', encoding='utf-8') as out:
            json.dump(wardata, out, ensure_ascii=False)


def save_latest_data(wardata, monitor):
    if wardata:
        save_wardata(wardata)
        with open('latest_downloaded_wardata.json',
                  'w', encoding='utf-8') as out:
            json.dump(wardata, out, ensure_ascii=False)
