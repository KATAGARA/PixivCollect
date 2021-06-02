import functools
import os
from tqdm import tqdm
import sys
import pymongo
import json


def image_filter(f):
    f = f.split('.')
    if len(f) != 2 or f[1] not in ['jpg', 'png', 'gif']:
        return False
    f = f[0].split('_p')
    if len(f) != 2 or not (f[0].isdigit() and f[1].isdigit()):
        return False
    return True


def comp(x, y):
    x_sp = x.split('_')
    y_sp = y.split('_')
    x_id = int(x_sp[0])
    y_id = int(y_sp[0])
    if x_id < y_id:
        return -1
    elif x_id > y_id:
        return 1
    else:
        x_p = x_sp[1].split('.')[0]
        y_p = y_sp[1].split('.')[0]
        x_num = int(x_p.split('p')[1])
        y_num = int(y_p.split('p')[1])
        if x_num < y_num:
            return -1
        elif x_num > y_num:
            return 1
        else:
            return 1


def image_file_analyse(path, use_pbar, db_port, db_name):
    db_illust = pymongo.MongoClient('mongodb://localhost:' + str(db_port))[db_name].illust
    files = os.listdir(path)
    files = list(filter(image_filter, files))
    pbar = tqdm(total=len(files)) if use_pbar is True else None
    files.sort(key=functools.cmp_to_key(comp))

    res = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    group_type = None
    group_id = None
    skip = False
    for file in files:
        if use_pbar:
            pbar.update(1)
        illust_id = int(file.split('_')[0])
        if group_id != illust_id:
            skip = False
            group_id = illust_id
            illust = db_illust.find_one({'illust_id': illust_id})
            if not illust:
                skip = True
                continue
            group_type = illust['illust_type']
            res[group_type][0] += 1
        if skip:
            continue
        res[group_type][1] += 1
        res[group_type][2] += os.path.getsize(os.path.join(path, file))

    res = {
        "illust": {"album": res[0][0], "image": res[0][1], "size": res[0][2]},
        "manga":  {"album": res[1][0], "image": res[1][1], "size": res[1][2]},
        "ugoira": {"album": res[2][0], "image": res[2][1], "size": res[2][2]}
    }
    print(json.dumps(res))
