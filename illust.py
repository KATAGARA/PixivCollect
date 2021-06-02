import multiprocessing
import re
import time

import pymongo
import retrying

import utils


class Illust:
    __user_agent = r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
                   '(KHTML, like Gecko) Chrome/86.0.4240.80 Safari/537.36 Edg/86.0.622.43'
    __url = 'https://www.pixiv.net/ajax/illust/'

    __headers = {'Connection': 'close', 'User-Agent': __user_agent, 'Cookie': utils.cookie, }
    # __db = pymongo.MongoClient('mongodb://localhost:27017').Tet
    # __db = pymongo.MongoClient('mongodb://localhost:27017').Pixiv
    # __db_illust = __db.illust
    # __db_author = __db.author
    # __db_tag = __db.tag
    # __db_gif_meta = __db.gif_meta
    # __db_image = __db.image

    __norm_referer = 'https://www.pixiv.net/member_illust.php?mode=medium&illust_id='
    __gif_referer = 'https://www.pixiv.net/artworks/'

    def __init__(self, in_queue, out_queue, done_pipe, message_pipe, db_port='27017', db_name='Pixiv', process_num=10):
        # self.__check_args(in_queue, out_queue, num_process)
        self.__in_queue = in_queue
        self.__out_queue = out_queue
        self.__done_pipe = done_pipe
        self.__message_pipe = message_pipe
        self.__db_name = db_name
        self.__db_port = db_port
        self.__process_num = process_num
        self.pid = []

    def start(self):
        process_list = []
        for i in range(self.__process_num):
            process_list.append(multiprocessing.Process(target=self.handle_illust, name='illust-%d' % i))

        for process in process_list:
            process.start()
            self.pid.append(process.pid)

    def handle_illust(self):
        db = pymongo.MongoClient('mongodb://localhost:' + str(self.__db_port))[self.__db_name]
        while True:
            illust_params = self.__in_queue.get()
            if illust_params is None:
                break
            illust_id, is_save_image = illust_params[0], illust_params[1]
            is_download_image_even_saved = len(illust_params) == 3 and illust_params[2] == 'download_image_even_saved'
            is_not_save_manga = len(illust_params) == 3 and illust_params[2] == 'not_save_manga'
            illust_info = self.__get_illust_info(illust_id)
            illust = self.__handle_illust_info(illust_info)
            self.__write_db_illust(illust, db)
            is_save_image = False if is_not_save_manga and illust['illust_type'] == 1 else is_save_image
            if not is_save_image and not is_download_image_even_saved:
                self.__message_pipe.send('-ril')
                continue

            is_save_image = True
            image_doc = self.get_image_db_document_by_id(illust_id, db)
            if image_doc is None:
                self.__write_db_image_add_new(illust_id, illust['page_count'], illust['upload_date'], db)
            else:
                if image_doc['page_count'] != len(image_doc['image_list']) \
                        or (illust['illust_type'] != 2 and image_doc['page_count'] != illust['page_count']):
                    self.__write_db_image_set_empty(illust_id, illust['page_count'], illust['upload_date'], db)
                elif illust['create_date'] == illust['upload_date']:
                    if image_doc['time'] == 'history':
                        self.__write_db_image_change_history_time(illust_id, illust['upload_date'], db)
                        is_save_image = False
                    elif image_doc['time'] == illust['upload_date']:
                        is_save_image = False
                    else:
                        raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: "
                                            "handle_illust %d image_db time 异常 [%s %s]"
                                            % (illust['illust_id'], image_doc['time'], illust['upload_time']))
                elif illust['create_date'] != illust['upload_date']:
                    if image_doc['time'] == 'history':
                        self.__write_db_image_set_empty(illust_id, illust['page_count'], illust['upload_date'], db)
                    elif image_doc['time'] == illust['upload_date']:
                        is_save_image = False
                    elif image_doc['time'] != illust['upload_date']:
                        self.__write_db_image_set_empty(illust_id, illust['page_count'], illust['upload_date'], db)
                    else:
                        raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: "
                                            "handle_illust %d image_db time 异常 [%s %s]"
                                            % (illust_id, image_doc['time'], illust['upload_time']))

            msg = 'not_write_db_image' if (not is_save_image and is_download_image_even_saved) else ''
            if is_save_image or is_download_image_even_saved:
                self.__message_pipe.send('+dil')
                # print(illust)
                # print(is_save_image, is_download_image_even_saved, is_not_save_manga)
                # print(illust_params)
                if illust['illust_type'] != 2:
                    match_res = re.match('(.*/)(.*)_.*?\.(.*)', illust['url_original'])
                    for i in range(illust['page_count']):
                        image_save_name = '%s_p%d.%s' % (match_res[2], i, match_res[3])
                        self.__message_pipe.send('+dim')
                        # print([illust_id, image_save_name, match_res[1] + image_save_name, msg])
                        self.__out_queue.put([illust_id, image_save_name, match_res[1] + image_save_name, msg])
                else:
                    gif_meta = self.__get_gif_meta(illust_id)
                    if is_save_image:
                        self.__write_db_gif_meta(illust_id, gif_meta, db)
                        self.__write_db_image_change_page_count(illust_id, len(gif_meta['frames']), db)
                    if illust['page_count'] != 1:
                        raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: "
                                            "handle_illust %d gif 张数大于1" % illust_id)

                    match_res = re.match('.*/((.*)_(.*))', gif_meta['originalSrc'])
                    save_name = "%s_%s" % (match_res[2], match_res[3])
                    self.__message_pipe.send('+diz')
                    # print([illust_id, save_name, gif_meta['originalSrc'], msg])
                    self.__out_queue.put([illust_id, save_name, gif_meta['originalSrc'], msg])

            self.__message_pipe.send('-ril')
        self.__done_pipe.send('done')

    @staticmethod
    def __get_gif_meta(illust_id):
        url = 'https://www.pixiv.net/ajax/illust/{}/ugoira_meta'.format(illust_id)
        headers = {'Connection': 'close', 'User-Agent': Illust.__user_agent, 'Cookie': Illust.__cookie}
        while True:
            try:
                gif_meta_response = utils.request(url, headers, 'gif meta failed: %d' % illust_id)
                gif_meta = gif_meta_response.json()['body']
            except BaseException as e:
                # todo
                print(e)
            else:
                break
        return gif_meta

    @staticmethod
    def get_image_db_document_by_id(illust_id, db):
        return db.image.find_one({'illust_id': illust_id})

    @staticmethod
    @retrying.retry
    def __get_illust_info(illust_id):
        url = 'https://www.pixiv.net/ajax/illust/' + str(illust_id)
        illust_info_response = utils.request(url, Illust.__headers)
        return illust_info_response.json()['body']

    @staticmethod
    @retrying.retry
    def __get_gif_meta(illust_id):
        url = 'https://www.pixiv.net/ajax/illust/{}/ugoira_meta'.format(illust_id)
        gif_meta_response = utils.request(url, Illust.__headers)
        return gif_meta_response.json()['body']

    @staticmethod
    def __handle_illust_info(illust_info):
        tags = []
        tags_json = illust_info['tags']['tags']
        for i in range(len(tags_json)):
            tags.append(tags_json[i]['tag'])
        return {
            'illust_id': int(illust_info['illustId']),
            'r18': 2 if ('R-18G' in tags) else (1 if ('R-18' in tags) else 0),
            'tags': tags,
            'page_count': int(illust_info['pageCount']),
            'like_count': int(illust_info['likeCount']),
            'bookmark_count': int(illust_info['bookmarkCount']),
            'view_count': int(illust_info['viewCount']),
            'width': int(illust_info['width']),
            'height': int(illust_info['height']),
            "illust_type": int(illust_info['illustType']),
            'illust_title': illust_info['illustTitle'],
            'author_id': int(illust_info['userId']),
            'author_name': illust_info['userName'],
            'description': illust_info['description'],
            'url_original': illust_info['urls']['original'],
            'create_date': illust_info['createDate'],
            'upload_date': illust_info['uploadDate'],
            'update_info_date': time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime()),
        }

    @staticmethod
    def __write_db_illust(illust, db):
        """
        illust_type: 0->illust 1->manga 2->ugoira
        :param illust:
        :return:
        """
        res = db.illust.find_one({'illust_id': illust['illust_id']})
        if res is None:
            db.illust.insert_one(illust)
            Illust.__write_db_tag(illust['tags'], db)
            Illust.__write_db_author(illust['author_id'], illust['author_name'], illust['illust_id'], db)
        else:
            db.illust.replace_one({'illust_id': illust['illust_id']}, illust)

    @staticmethod
    def __write_db_tag(tags, db):
        for tag in tags:
            db.tag.update_many({'tag': tag}, {'$inc': {'count': 1}}, upsert=True)

    @staticmethod
    def __write_db_author(author_id, author_name, illust_id, db):
        db.author.update_one(
            {'author_id': author_id},
            {'$set': {'author_name': author_name}, '$addToSet': {'artworks': illust_id}}, upsert=True)

    @staticmethod
    def __write_db_gif_meta(illust_id, gif_meta, db):
        delay = []
        delay_json = gif_meta['frames']
        for i in range(len(delay_json)):
            delay.append(delay_json[i]['delay'])

        data = {
            'illust_id': illust_id,
            'original_src': gif_meta['originalSrc'],
            'image_type': gif_meta['mime_type'],
            'delay': delay,
        }
        res = db.gif_meta.find({'illust_id': illust_id}).count()
        if res == 0:
            db.gif_meta.insert_one(data)
        elif res == 1:
            db.gif_meta.replace_one({'illust_id': illust_id}, data)
        return data

    @staticmethod
    def __write_db_image_add_new(illust_id, page_count, date, db):
        data = {
            'illust_id': illust_id,
            'page_count': page_count,
            'image_list': [],
            'time': date,
        }
        db.image.insert_one(data)

    @staticmethod
    def __write_db_image_set_empty(illust_id, page_count, date, db):
        data = {
            'illust_id': illust_id,
            'page_count': page_count,
            'image_list': [],
            'time': date,
        }
        db.image.replace_one({'illust_id': illust_id}, data)

    @staticmethod
    def __write_db_image_change_history_time(illust_id, date, db):
        db.image.update_one({'illust_id': illust_id}, {"$set": {"time": date}})

    @staticmethod
    def __write_db_image_change_page_count(illust_id, page_count, db):
        db.image.update_one({'illust_id': illust_id}, {"$set": {"page_count": page_count}})

    @staticmethod
    def __check_args(in_queue, out_queue, num_process):
        # if type(in_queue) != multiprocessing.Queue().__class__:
        #     raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __check_args in_queue type error. "
        #                         "query:%s use:%s" % (multiprocessing.Queue().__class__, type(in_queue)))
        # if type(out_queue) != bool:
        #     raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __check_args out_queue type error. "
        #                         "query:%s use:%s" % (multiprocessing.Queue().__class__, type(out_queue)))
        if type(num_process) != int:
            raise BaseException("~~~~~~~~~~自定义错误~~~~~~~~~~~: __check_args num_process type error. "
                                "query:int use:%s" % type(num_process))
