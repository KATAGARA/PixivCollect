import argparse
import json
import sys
import pixiv_collect
from get_db_info import get_db_info
from image_files_analyse import image_file_analyse
from image_move import image_move
import multiprocessing


def parser_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--type', type=str, choices=['info', 'gdi', 'ifa', 'im', 'pc'],
                        help='gdi is get_db_info, ifa is image_file_analyse, im is image_move, pc is pixiv_collect')
    parser.add_argument('--src', type=str, help='图片移动源目录')
    parser.add_argument('--tra', type=str, help='图片移动目标目录')
    parser.add_argument('-m',  '--mode', type=str, help='图片移动模式', choices=['keep', 'move'])
    parser.add_argument('-md', '--moveDate', type=str, help='移动图片的图片日期')
    parser.add_argument('-p',  '--path', type=str, default=r'E://Pixiv//')
    parser.add_argument('-pb', '--pbar', type=str, default='T', choices=['T', 'F'], help='使用进度条')
    parser.add_argument('-db', '--dbName', type=str, default='Pixiv', help='数据库名')
    parser.add_argument('-pt', '--port', type=str, default='27017', help='MongoDB端口')
    parser.add_argument('-d',  '--date', type=int)
    parser.add_argument('-pa', '--params', type=str, default='default', help='排行榜参数')
    parser.add_argument('-wr', '--waitRank', type=str, default='T', choices=['T', 'F'], help='等待排行榜更新')
    parser.add_argument('-pn', '--progressNum', type=str, default=[2, 8, 15], help='进程数')
    return parser.parse_args()


if __name__ == '__main__':
    multiprocessing.freeze_support()
    args = parser_args()
    if args.type is None:
        pixiv_collect.newest()
    elif args.type == 'info':
        print('pixiv_collect 0.0.1')
    elif args.type == 'gdi':
        get_db_info(args.port, args.dbName)
    elif args.type == 'ifa':
        image_file_analyse(args.path, args.pbar == 'T', args.port, args.dbName)
    elif args.type == 'im':
        if args.src and args.tra and args.mode and args.moveDate:
            image_move(args.src, args.tra, args.mode, json.loads(args.moveDate),
                       args.pbar == 'T', args.port, args.dbName)
    elif args.type == 'pc':
        if args.date is not None:
            pixiv_collect.pixiv_collect(args.date, args.params, args.path, args.pbar,
                                        args.waitRank, args.port, args.dbName, args.progressNum)
    else:
        raise BaseException("sys.argv错误 %s", sys.argv)

