import multiprocessing
import os
import shutil
import zipfile
import copy

# import PIL.Image
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
# import cv2
from cv2 import imread as cv2read
import pymongo

import utils


class Image:

    __user_agent = r'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' \
                   '(KHTML, like Gecko) Chrome/86.0.4240.80 Safari/537.36 Edg/86.0.622.43'
    __headers = {'Connection': 'close', 'User-Agent': __user_agent, 'Cookie': utils.cookie}
    __norm_referer = 'https://www.pixiv.net/member_illust.php?mode=medium&illust_id='
    __gif_referer = 'https://www.pixiv.net/artworks/'

    # __db_image = pymongo.MongoClient('mongodb://localhost:27017').Tet.image
    # __db_image = pymongo.MongoClient('mongodb://localhost:27017').Pixiv.image

    def __init__(self, in_queue, done_pipe, message_pipe, db_port='27017',
                 db_name='Pixiv', process_num=20, save_path=r'E://Pixiv//'):
        self.__in_queue = in_queue
        self.__done_pipe = done_pipe
        self.__message_pipe = message_pipe
        self.__db_name = db_name
        self.__db_port = db_port
        self.__process_num = process_num
        self.__save_path = save_path
        self.pid = []

    def start(self):
        process_list = []
        for i in range(self.__process_num):
            process_list.append(multiprocessing.Process(target=self.handle_image, name='image-%d' % i))

        for process in process_list:
            process.start()
            self.pid.append(process.pid)

    def handle_image(self):
        db = pymongo.MongoClient('mongodb://localhost:' + str(self.__db_port))[self.__db_name]
        while True:
            image_params = self.__in_queue.get()
            if image_params is None:
                break
            illust_id, image_name, download_url, msg = (image_params[_] for _ in range(4))
            file_path = os.path.join(self.__save_path, image_name)
            is_write_db = msg != 'not_write_db_image'
            is_gif = True if image_name.endswith('zip') else False

            headers = copy.deepcopy(Image.__headers)
            headers['Referer'] = (Image.__gif_referer if is_gif else Image.__norm_referer) + str(illust_id)

            try_time = 0
            while True:
                image = utils.request(download_url, headers).content
                with open(file_path, 'wb') as file:
                    file.write(image)
                if self.__check_image_from_file(file_path):
                    break
                try_time += 1
                if try_time > 5:
                    break

            if is_write_db:
                if not is_gif:
                    Image.__write_db_image_add_image_file(illust_id, file_path, image_name, db)
                if is_gif:
                    r_params = self.__handle_gif_zip(illust_id, image_name)
                    for i in range(r_params[0]):
                        gif_file_name = '%d_p%d.%s' % (illust_id, i, r_params[1])
                        gif_file_path = os.path.join(self.__save_path, gif_file_name)
                        Image.__write_db_image_add_image_file(illust_id, gif_file_path, gif_file_name, db)
            elif is_gif:
                self.__handle_gif_zip(illust_id, image_name)

            self.__message_pipe.send('-dim')
        self.__done_pipe.send('done')

    def __handle_gif_zip(self, illust_id, zip_name):
        zip_file_path = os.path.join(self.__save_path, zip_name)
        zip_file = zipfile.ZipFile(zip_file_path)
        image_list = zip_file.namelist()
        image_list.sort()

        out_path_t = os.path.join(self.__save_path, str(illust_id) + '/')
        zip_file.extractall(out_path_t)
        suffix = image_list[0].split('.')[1]
        for i, v in enumerate(image_list):
            shutil.copy2(out_path_t + v, os.path.join(self.__save_path, '%d_p%d.%s' % (illust_id, i, suffix)))

        zip_file.close()
        while True:
            try:
                os.remove(zip_file_path)
            except PermissionError as e:
                pass
            else:
                break
        shutil.rmtree(out_path_t)
        return len(image_list), suffix

    @staticmethod
    def check_image(image):
        if image.startswith(b'\xff\xd8\xff'):  # .jpg
            return image.endswith(b'\xff\xd9')
        elif image.startswith(b'\x89\x50\x4e\x47'):  # .png
            return image.endswith(b'\xae\x42\x60\x82')
        elif image.startswith(b'\x47\x49\x46\x38'):  # .gif
            return image.endswith(b'\x00\x3b')
        elif image.startswith(b'\x50\x4b\x03\x04'):  # .zip
            return image[-22:-18] == b'\x50\x4b\x05\x06'
        else:
            return False

    @staticmethod
    def __check_image_from_file(file_path):
        if file_path.endswith('zip'):
            return zipfile.is_zipfile(file_path)
        with open(file_path, 'rb') as file:
            image = file.read()
            if image.startswith(b'\xff\xd8\xff'):        # .jpg
                return image.endswith(b'\xff\xd9')
            elif image.startswith(b'\x89\x50\x4e\x47'):  # .png
                return image.endswith(b'\xae\x42\x60\x82')
            elif image.startswith(b'\x47\x49\x46\x38'):  # .gif
                return image.endswith(b'\x00\x3b')
            else:
                return False

    @staticmethod
    def get_image_size(file_path):
        try:
            i_size = PILImage.open(file_path).size
        except (UnidentifiedImageError, ValueError):
            try:
                size_t = cv2read(file_path).shape
                i_size = (size_t[1], size_t[0])
            except AttributeError:
                i_size = (-1, -1)
                with open('error_image.txt', 'a') as ff:
                    ff.write(file_path + '\n')
        return i_size

    @staticmethod
    def __write_db_image_add_image_file(illust_id, file_path, image_name, db):
        size = Image.get_image_size(file_path)
        if size[0] != -1 and size[1] != -1:
            data = {
                'name': image_name,
                'width': size[0],
                'height': size[1],
                'size': os.path.getsize(file_path)
            }
            db.image.update_one({'illust_id': illust_id}, {'$addToSet': {'image_list': data}})

