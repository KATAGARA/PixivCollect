import itertools
import shutil
from tqdm import tqdm
import pymongo
import os


def get_rank_params_group_default():
    params_list = [[['overall', 'illust', 'ugoira'], ['daily'], ['', 'r18']],
                   [['overall', 'illust'], ['weekly'], ['r18g']],
                   [['overall', 'illust', 'ugoira'], ['weekly'], ['', 'r18']],
                   [['overall', 'illust'], ['monthly'], ['']],
                   [['overall'], ['original'], ['']],
                   [['overall'], ['male'], ['', 'r18'], ['manga']],
                   [['overall', 'illust'], ['rookie'], [''], ['manga']]]


def get_mode_group(mode):
    mode_list = []
    if mode == 'default':
        mode_list = [['overall_daily', 'overall_weekly', 'overall_monthly', 'overall_original',
                      'illust_daily', 'illust_weekly', 'illust_monthly', 'ugoira_daily', 'ugoira_weekly'],
                     [['overall_male', 'manga'], ['overall_rookie', 'manga'], ['illust_rookie', 'manga']]]
    elif mode == 'all':
        mode_list = [['overall_daily', 'overall_weekly', 'overall_monthly', 'overall_original', 'overall_male',
                      'overall_rookie', 'overall_female', 'illust_daily', 'illust_weekly', 'illust_monthly',
                      'illust_rookie', 'ugoira_daily', 'ugoira_weekly', 'manga_daily', 'manga_weekly', 'manga_monthly',
                      'manga_rookie']]
    return mode_list


def shutil_try(src, tra, mode):
    while True:
        try:
            if mode == 'move':
                shutil.move(src, tra)
            elif mode == 'copy':
                shutil.copy2(src, tra)
        except BaseException as e:
            pass
        else:
            break


def get_illust_id_list_one_day(mode_list, rank_date, db):
    illust_id_list = []
    for mode in mode_list[0]:
        ranks = db[mode].find({'rank_date': rank_date})
        for rank in ranks:
            illust_id_list.append(rank['illust_id'])
    if len(mode_list) == 2:
        for mode in mode_list[1]:
            ranks = db[mode[0]].find({'rank_date': rank_date})
            for rank in ranks:
                illust_id = rank['illust_id']
                illust = db['illust'].find_one({'illust_id': illust_id})
                try:
                    if illust['illust_type'] != 1:
                        illust_id_list.append(illust_id)
                except TypeError as e:
                    print(illust_id, mode)
    return illust_id_list


def get_illust_id_set(mode_list, rank_date_list, db):
    illust_id_set = set()
    for rank_date in rank_date_list:
        for illust_id in get_illust_id_list_one_day(mode_list, rank_date, db):
            illust_id_set.add(illust_id)
    return illust_id_set


def image_file_move(src, tra, mode, rank_date_list, use_pbar, db):
    illust_id_set = get_illust_id_set(get_mode_group('all'), rank_date_list, db)
    if mode == 'keep':
        files = os.listdir(src)
        pbar = tqdm(total=len(files)) if use_pbar else None
        for file in files:
            illust_id = int(file.split('_')[0])
            if illust_id in illust_id_set:
                shutil_try(os.path.join(src, file), os.path.join(tra, file), 'copy')
            else:
                shutil_try(os.path.join(src, file), os.path.join(tra, file), 'move')
            if pbar:
                pbar.update(1)
    elif mode == 'move':
        pbar = tqdm(total=len(illust_id_set)) if use_pbar else None
        for illust_id in illust_id_set:
            image = db['image'].find_one({'illust_id': illust_id})
            if image is None:
                if pbar:
                    pbar.update(1)
                continue
            for image_file in image['image_list']:
                image_name = image_file['name']
                if os.path.exists(os.path.join(src, image_name)) and not os.path.exists(os.path.join(tra, image_name)):
                    shutil_try(os.path.join(src, image_name), os.path.join(tra, image_name), 'copy')
            if pbar:
                pbar.update(1)


def image_move(src, tra, mode, rank_date, use_pbar, db_port, db_name):
    db = pymongo.MongoClient('mongodb://localhost:' + str(db_port))[db_name]
    if type(rank_date) == int:
        rank_date_list = [rank_date]
    elif type(rank_date) == tuple:
        rank_date_list = list(range(rank_date[0], rank_date[1] + 1))
    else:
        rank_date_list = rank_date
    print(rank_date_list)
    if mode == 'keep':
        image_file_move(src, tra, 'keep', rank_date_list, use_pbar, db)
    elif mode == 'move':
        image_file_move(src, tra, 'move', rank_date_list, use_pbar, db)
