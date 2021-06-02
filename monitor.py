import multiprocessing
import os
import time

import pymongo
from tqdm import tqdm

from illust import Illust
from image import Image
from rank import Rank


class Monitor:

    def __init__(self, date, params_list='default', save_path=r'E://Pixiv//',
                 use_pbar=True, is_wait_rank=False, db_port='27017', db_name='Pixiv', process_num=None):
        self.__db_port = db_port
        self.__db_name = db_name
        self.__save_path = save_path
        self.__date = date
        self.__use_pbar = use_pbar
        self.__wait_rank = is_wait_rank
        self.__list_process_num = 2 if process_num is None else process_num[0]
        self.__illust_process_num = 8 if process_num is None else process_num[1]
        self.__image_process_num = 15 if process_num is None else process_num[2]
        self.__params_list = params_list

    def start(self):
        start_time = time.time()

        if not os.path.exists(self.__save_path):
            os.makedirs(self.__save_path)

        manager = multiprocessing.Manager()
        illust_queue = manager.Queue()
        image_queue = manager.Queue()
        illust_id_list = manager.list()
        list_done_pipe, list_message_pipe, illust_done_pipe, illust_message_pipe, \
            image_done_pipe, image_message_pipe = (multiprocessing.Pipe(duplex=False) for _ in range(6))

        rank = Rank(illust_queue, list_done_pipe[1], list_message_pipe[1], illust_id_list,
                    self.__date, self.__params_list, self.__db_port, self.__db_name,
                    process_num=self.__list_process_num, is_wait_rank=self.__wait_rank)

        illust = Illust(illust_queue, image_queue, illust_done_pipe[1], illust_message_pipe[1],
                        self.__db_port, self.__db_name, process_num=self.__illust_process_num)

        image = Image(image_queue, image_done_pipe[1], image_message_pipe[1],
                      self.__db_port, self.__db_name, process_num=self.__image_process_num, save_path=self.__save_path)

        rank.start()
        illust.start()
        image.start()

        list_tqdm = tqdm(total=0, desc='list  ') if self.__use_pbar else None
        illust_tqdm = tqdm(total=0, desc='illust') if self.__use_pbar else None
        image_tqdm = tqdm(total=0, desc='image ') if self.__use_pbar else None

        pipes = [list_done_pipe[0], list_message_pipe[0], illust_done_pipe[0],
                 illust_message_pipe[0], image_done_pipe[0], image_message_pipe[0]]

        flag = False
        list_process_num = self.__list_process_num
        illust_process_num = self.__illust_process_num
        image_process_num = self.__image_process_num
        total_illust = 0
        real_illust = 0
        download_illust = 0
        download_image = 0
        download_gif = 0
        while pipes:
            for r in multiprocessing.connection.wait(pipes):
                try:
                    msg = r.recv()
                    if r == list_message_pipe[0]:
                        if msg == '+ril':
                            total_illust += 1
                            real_illust += 1
                            if self.__use_pbar:
                                illust_tqdm.total += 1
                                illust_tqdm.update(0)
                            else:
                                print('+ril', flush=True)
                        elif msg == '+til':
                            total_illust += 1
                        elif msg == '-l':
                            if self.__use_pbar:
                                list_tqdm.update(1)
                            else:
                                print('-l', flush=True)
                        elif str(msg).startswith('list'):
                            if self.__use_pbar:
                                list_tqdm.total += int(str(msg)[4:])
                                list_tqdm.update(0)
                            else:
                                print(msg, flush=True)
                    elif r == illust_message_pipe[0]:
                        if msg == '-ril':
                            if self.__use_pbar:
                                illust_tqdm.update(1)
                            else:
                                print('-ril', flush=True)
                        elif msg == '+dil':
                            download_illust += 1
                        elif msg == '+dim':
                            download_image += 1
                            if self.__use_pbar:
                                image_tqdm.total += 1
                                image_tqdm.update(0)
                            else:
                                print('+dim', flush=True)
                        elif msg == '+diz':
                            download_gif += 1
                            if self.__use_pbar:
                                image_tqdm.total += 1
                                image_tqdm.update(0)
                            else:
                                print('+diz', flush=True)
                    elif r == image_message_pipe[0]:
                        if msg == '-dim':
                            if self.__use_pbar:
                                image_tqdm.update(1)
                            else:
                                print('-dim', flush=True)

                    elif r == list_done_pipe[0]:
                        list_process_num -= 1
                        if list_process_num == 0:
                            for _ in range(self.__illust_process_num):
                                illust_queue.put(None)
                            if not self.__use_pbar:
                                print('list-done', flush=True)
                            # self.__list_done_pipe[0].close()
                    elif r == illust_done_pipe[0]:
                        illust_process_num -= 1
                        if illust_process_num == 0:
                            for _ in range(self.__image_process_num):
                                image_queue.put(None)
                            if not self.__use_pbar:
                                print('illust-done', flush=True)
                            # self.__illust_done_pipe[0].close()
                    elif r == image_done_pipe[0]:
                        image_process_num -= 1
                        if image_process_num == 0:
                            flag = True
                            if not self.__use_pbar:
                                print('image-done', flush=True)
                            break
                except EOFError:
                    print(r, flush=True)
                    pipes.remove(r)
            if flag:
                break

        if self.__use_pbar:
            list_tqdm.close()
            illust_tqdm.close()
            image_tqdm.close()
        end_time = time.time()
        self.__write_db_log('rank', self.__date, 'default', total_illust, real_illust,
                            download_illust, download_image, download_gif, int(end_time - start_time))
        if self.__use_pbar:
            print('---------- %s %s  %d  done, ti %d , ri %d , di %d , image %d , gif %d , use_time: %d ---------'
                  % ('mode', 'default', self.__date, total_illust, real_illust,
                     download_illust, download_image, download_gif, int(end_time - start_time)), end='\n\n', flush=True)

    def __write_db_log(self, mode, rank_date, params, total_illust, real_illust,
                       download_illust, download_image, download_gif, use_time):
        log = {
            'mode': mode,
            'rank_date': rank_date,
            'params': params,
            'total_illust': total_illust,
            'real_illust': real_illust,
            'download_illust': download_illust,
            'download_image': download_image,
            'download_gif': download_gif,
            'use_time': use_time,
            'finish_time': time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        }
        pymongo.MongoClient('mongodb://localhost:' + str(self.__db_port))[self.__db_name].log.insert_one(log)

    # def __handle_params(self, mode, params):
    #     if mode == 'rank':
    #         if type(params) == list:
    #             if len(params) == 2:
    #                 self.__date = params[0]
    #                 self.__rank_params_list = params[1]
    #             else:
    #                 raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __handle_params %s rank 参数错误" % params)
    #     elif mode == 'id_list':
    #         if type(pa)

