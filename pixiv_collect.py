import time
from datetime import datetime, timedelta
from monitor import Monitor
import json


def default(date):
    Monitor(date).start()


def newest():
    local_time = time.localtime(time.time())
    date_t = datetime(local_time.tm_year, local_time.tm_mon, local_time.tm_mday) - timedelta(1)
    Monitor(int(date_t.strftime('%Y%m%d')), is_wait_rank=True).start()


def pixiv_collect(date, params_list, save_path, use_pbar, is_wait_rank, db_port, db_name, process_num):
    params_list = params_list if params_list in ['default', 'all'] else json.loads(params_list.replace('!', '"'))
    process_num = process_num if type(process_num) is list else json.loads(process_num)
    use_pbar = use_pbar == 'T'
    is_wait_rank = is_wait_rank == 'T'
    Monitor(date, params_list, save_path, use_pbar, is_wait_rank, db_port, db_name, process_num).start()
