import itertools
import multiprocessing
import time

import pymongo
import retrying
from urllib.parse import urlencode
import utils


class Rank:
    """

    Args:
        :param out_queue: 结果输出到的JoinableQueue实例, 结果eg: {id: 49592218, save_image: True}
        :param params: rank参数 type: string|list, eg: 'default', [['overall'], ['original'], [''], true], todo
        :param date:
    """

    __user_agent = r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
                   '(KHTML, like Gecko) Chrome/86.0.4240.80 Safari/537.36 Edg/86.0.622.43'
    __url = r'https://www.pixiv.net/ranking.php'
    # with open('cookie.txt', 'r') as f:
    #     __cookie = f.read()

    __ONLY_SAVE_INFO = 0
    __SAVE_INFO_AND_IMAGE = 1
    __MAX_INDEX = 100
    # __db = pymongo.MongoClient('mongodb://localhost:27017').Tet
    # __db = pymongo.MongoClient('mongodb://localhost:27017').Pixiv

    def __init__(self, out_queue, done_pipe, message_pipe, illust_id_list, date, params,
                 db_port='27017', db_name='Pixiv', process_num=2, is_wait_rank=False):
        # self.__check_args(out_queue, process_num)
        self.__out_queue = out_queue
        self.__done_pipe = done_pipe
        self.__message_pipe = message_pipe
        self.__illust_id_list = illust_id_list

        self.__date = self.__check_date(date)
        self.__params_list = self.__handle_params(params)
        self.__db_name = db_name
        self.__db_port = db_port
        self.__process_num = process_num
        self.__is_wait_rank = is_wait_rank
        self.pid = []

    def start(self):
        queue = multiprocessing.Queue()
        self.__message_pipe.send('list' + str(len(self.__params_list)))
        for params in self.__params_list:
            queue.put(params)

        process_list = []
        for i in range(self.__process_num):
            queue.put(None)
            process_list.append(multiprocessing.Process(target=self.handle_rank_list,
                                                        args=(queue,), name='rank-%d' % i))
        for process in process_list:
            process.start()
            self.pid.append(process.pid)

    def handle_rank_list(self, queue):
        db = pymongo.MongoClient('mongodb://localhost:' + str(self.__db_port))[self.__db_name]
        while True:
            q_params = queue.get()
            if q_params is None:
                break
            if self.__check_date_overstep_mode_range(self.__date, q_params[0], q_params[1], q_params[2]):
                self.__message_pipe.send('-l')
                continue

            illust_mode, rank_mode, r18, save_flag = q_params[0], q_params[1], q_params[2], q_params[3]
            mode = rank_mode if r18 == '' else ('r18g' if r18 == 'r18g' else rank_mode + '_r18')

            params = {'mode': mode, 'date': str(self.__date), 'format': 'json', }
            if illust_mode != 'overall':
                params['content'] = illust_mode

            headers = {'Connection': 'close', 'User-Agent': self.__user_agent}
            if r18 in ['r18', 'r18g']:
                headers['Cookie'] = utils.cookie

            newest_page = Rank.__return_newest_rank_page(illust_mode, rank_mode, r18) if self.__is_wait_rank else None
            monthly_try_time = 0
            page = 1
            while page < Rank.__MAX_INDEX:
                params['p'] = page
                request_url = '%s?%s' % (self.__url, urlencode(params))
                response = self.__get_rank_one_page(request_url, headers)

                if type(response) == int:
                    if response == 404:
                        if page == 1:
                            if self.__is_wait_rank:
                                time.sleep(20)
                                continue
                            else:
                                raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __handle_rank_list %s 无图片错误" % params)
                        elif self.__is_wait_rank and page < newest_page:
                            time.sleep(5)
                            if rank_mode == 'monthly':
                                monthly_try_time += 1
                                time.sleep(5)
                                if monthly_try_time > 10:
                                    with open('error_rank.txt', 'a') as ff:
                                        ff.write("%s %s %s %d %d" % (illust_mode, rank_mode, r18, self.__date, page))
                                    break
                            continue
                        else:
                            break
                    else:
                        raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __handle_rank_list  %s 请求结果错误" % str(response))
                else:
                    for illust in response:
                        if illust['illust_id'] not in self.__illust_id_list:
                            is_save_image = save_flag[int(illust['illust_type'])] == 1
                            if is_save_image:
                                self.__illust_id_list.append(illust['illust_id'])
                            self.__message_pipe.send('+ril')
                            self.__out_queue.put((illust['illust_id'], is_save_image))
                        else:
                            self.__message_pipe.send('+til')
                    self.__write_db_rank_info(response, illust_mode, rank_mode, r18, db)
                page += 1
                monthly_try_time = 0

            self.__message_pipe.send('-l')

        self.__done_pipe.send('done')

    def __write_db_rank_info(self, illusts, illust_mode, rank_mode, r18, db):
        for illust in illusts:
            rank_db = db['%s_%s' % (illust_mode, rank_mode)]
            data = {
                'illust_id': int(illust['illust_id']),
                'rank_date': self.__date,
                'rank': int(illust['rank']),
                'yes_rank': int(illust['yes_rank']),
                'r18': (0 if r18 == '' else (1 if r18 == 'r18' else 2))
            }
            res = rank_db.find(
                {'illust_id': data['illust_id'], 'rank_date': data['rank_date'], 'r18': data['r18']}).count()
            if res == 0:
                rank_db.insert_one(data)
            elif res != 1:
                raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: write_db_rank_info  %d %d %s  rank db 存在相同数据"
                                    % (data['illust_id'], data['rank_date'], r18))

    @staticmethod
    @retrying.retry
    def __get_rank_one_page(request_url, headers):
        response = utils.request(request_url, headers)
        # print(response.status_code, response.text)
        if response.status_code != 200:
            return response.status_code
        return response.json()['contents']

    def __handle_params(self, params):
        if type(params) == list:
            if len(params) in [4, 5] and type(params[3]) == int:
                self.__check_user_input_params(params)
                params_list = self.__get_rank_params_group(params)
            else:
                for v in params:
                    self.__check_user_input_params(v)
                params_list = self.__get_rank_params_group_multiple(params)
            for params in params_list:
                self.__check_mode_group(params)
            return params_list
        else:
            if params == 'default':
                return self.__get_rank_params_group_default()
            elif params == 'all':
                return self.__get_rank_params_group_all()

    @staticmethod
    def __check_user_input_params(params):
        flag = 0
        if len(params) < 4:
            flag = 1
        for index, value in enumerate(params):
            if index <= 2:
                if type(value) == list:
                    for v in value:
                        if type(v) != str:
                            flag = 2
                            break
                elif type(value) != str:
                    flag = 3
                    break
            elif index == 3:
                if value != 1 and value != 0:
                    flag = 4
                    break
            elif index == 4:
                if type(value) != list:
                    flag = 5
                    break
                else:
                    for v in value:
                        if v not in ['illust', 'ugoira', 'manga']:
                            flag = 6
                            break
        if flag != 0:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: check_user_input_params %d, %s 参数错误" % (flag, params))

    @staticmethod
    def __check_args(out_queue, num_process):
        # if type(out_queue) != multiprocessing.Queue().__class__:
        #     raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __check_args out_queue type error. "
        #                         "query:%s use:%s" % (multiprocessing.Queue().__class__, type(out_queue)))
        # todo num大于0
        if type(num_process) != int:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __check_args num_process type error. "
                                "query:int use:%s" % type(num_process))

    @staticmethod
    def __check_date(date):
        try:
            time.strptime(str(date), "%Y%m%d")
        except ValueError:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: check_date  %d 日期错误" % date)
        except BaseException as error:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: check_date  %d 未知错误")
        else:
            return date

    @staticmethod
    def __check_date_overstep_mode_range(date, illust_mode, rank_mode, r18):
        if illust_mode == 'overall':
            if rank_mode == 'daily' and date < 20070913:
                return True
            elif rank_mode in ['weekly', 'monthly'] and r18 in ['', 'r18'] and date < 20080415:
                return True
            elif rank_mode == 'weekly' and r18 == 'r18g' and date < 20090516:
                return True
            elif rank_mode == 'rookie' and date < 20100331:
                return True
            elif rank_mode in ['male', 'female'] and date < 20111012:
                return True
            elif rank_mode == 'original' and date < 20120502:
                return True
            else:
                return False
        elif illust_mode == 'illust' or illust_mode == 'manga':
            if rank_mode == 'daily' and date < 20101101:
                return True
            elif rank_mode in ['weekly', 'monthly', 'rookie'] and date < 20110623:
                return True
            else:
                return False
        elif illust_mode == 'ugoira':
            if rank_mode == 'daily' and date < 20140626:
                return True
            elif rank_mode == 'weekly' and date < 20140716:
                return True
            else:
                return False

    @staticmethod
    def __check_mode_group(*args):
        """
        判断 illust_mode, rank_mode, r18 组合是否正确
        :param args: eg: args=(['illust', 'daily', '']) | args=('illust', 'daily', '')
        """
        flag = False
        if len(args) == 1:
            illust_mode, rank_mode, r18 = args[0][0], args[0][1], args[0][2]
        else:
            illust_mode, rank_mode, r18 = args[0], args[1], args[2]

        if r18 == 'r18g' and rank_mode == 'weekly' and illust_mode in ['overall', 'illust', 'manga']:
            flag = True
        elif r18 == 'r18':
            if illust_mode in ['illust', 'ugoira', 'manga'] and rank_mode in ['daily', 'weekly']:
                flag = True
            elif illust_mode == 'overall' and rank_mode in ['daily', 'weekly', 'male', 'female']:
                flag = True
        elif r18 == '':
            if illust_mode == 'overall' and rank_mode in ['daily', 'weekly', 'monthly', 'rookie', 'original', 'male',
                                                          'female']:
                flag = True
            elif illust_mode in ['illust', 'manga'] and rank_mode in ['daily', 'weekly', 'monthly', 'rookie']:
                flag = True
            elif illust_mode == 'ugoira' and rank_mode in ['daily', 'weekly']:
                flag = True

        if not flag:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: "
                                "__check_mode_group %s %s %s mode组合错误" % (illust_mode, rank_mode, r18))

    @staticmethod
    def __return_newest_rank_page(i_m, r_m, r18):
        if (i_m == 'overall' and r18 == '' and r_m in ['daily', 'weekly', 'monthly', 'male', 'female']) \
                or (i_m == 'illust' and r18 == '' and r_m in ['daily', 'weekly']) \
                or (i_m == 'manga' and r18 == '' and r_m == 'daily'):
            return 10
        elif (i_m == 'overall' and r18 == '' and r_m in ['rookie', 'original']) \
                or (i_m == 'overall' and r18 == 'r18' and r_m in ['male', 'female']) \
                or (i_m == 'illust' and r18 == '' and r_m in ['rookie', 'monthly']):
            return 6
        elif (i_m in ['overall', 'illust', 'manga'] and r18 == 'r18' and r_m in ['daily', 'weekly']) \
                or (i_m == 'ugoira' and r18 == '' and r_m in ['daily', 'weekly']) \
                or (i_m == 'manga' and r18 == '' and r_m in ['weekly', 'monthly', 'rookie']):
            return 2
        elif (i_m in ['overall', 'illust', 'manga'] and r18 == 'r18g' and r_m == 'weekly') \
                or (i_m == 'ugoira' and r18 == 'r18' and r_m in ['daily', 'weekly']):
            return 1
        else:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: "
                                "__return_newest_rank_page %s %s %s mode组合错误" % (i_m, r_m, r18))

    @staticmethod
    def __get_rank_params_group(params):
        illust_m, rank_m, r18_m = map(lambda x: x if type(x) == list else [x], [params[0], params[1], params[2]])
        save_flag = [1, 1, 1] if params[3] != Rank.__ONLY_SAVE_INFO else [0, 0, 0]
        if len(params) == 5 and (params[3] != Rank.__ONLY_SAVE_INFO):
            if 'illust' in params[4]:
                save_flag[0] = 0
            if 'manga' in params[4]:
                save_flag[1] = 0
            if 'ugoira' in params[4]:
                save_flag[2] = 0
        return list(itertools.product(illust_m, rank_m, r18_m, [save_flag]))

    @staticmethod
    def __get_rank_params_group_multiple(params_list):
        params_group = []
        for params in params_list:
            params_group += Rank.__get_rank_params_group(params)
        return params_group

    @staticmethod
    def __get_rank_params_group_default():
        params_list = [[['overall', 'illust', 'ugoira'], ['daily'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust'], ['weekly'], ['r18g'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust', 'ugoira'], ['weekly'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust'], ['monthly'], [''], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall'], ['original'], [''], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall'], ['male'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE, ['manga']],
                       [['overall', 'illust'], ['rookie'], [''], Rank.__SAVE_INFO_AND_IMAGE, ['manga']],
                       [['overall'], ['female'], ['', 'r18'], Rank.__ONLY_SAVE_INFO],
                       [['manga'], ['daily', 'weekly', 'monthly', 'rookie'], [''], Rank.__ONLY_SAVE_INFO],
                       [['manga'], ['daily', 'weekly'], ['r18'], Rank.__ONLY_SAVE_INFO],
                       [['manga'], ['weekly'], ['r18g'], Rank.__ONLY_SAVE_INFO]]
        return Rank.__get_rank_params_group_multiple(params_list)

    @staticmethod
    def __get_rank_params_group_all():
        params_list = [[['overall', 'illust', 'ugoira'], ['daily'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust'], ['weekly'], ['r18g'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust', 'ugoira'], ['weekly'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust'], ['monthly'], [''], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall'], ['original'], [''], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall'], ['male'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall', 'illust'], ['rookie'], [''], Rank.__SAVE_INFO_AND_IMAGE],
                       [['overall'], ['female'], ['', 'r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['manga'], ['daily', 'weekly', 'monthly', 'rookie'], [''], Rank.__SAVE_INFO_AND_IMAGE],
                       [['manga'], ['daily', 'weekly'], ['r18'], Rank.__SAVE_INFO_AND_IMAGE],
                       [['manga'], ['weekly'], ['r18g'], Rank.__SAVE_INFO_AND_IMAGE]]
        return Rank.__get_rank_params_group_multiple(params_list)



