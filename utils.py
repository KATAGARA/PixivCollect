import os
import sys

import func_timeout
import requests
import retrying


@retrying.retry
@func_timeout.func_set_timeout(60)
def request(url, headers):
    # todo 输出消息
    return requests.get(url, headers=headers)


if os.path.exists('cookie.txt'):
    path = 'cookie.txt'
else:
    path = os.path.join(os.getcwd(), 'collect\\cookie.txt')
with open(path, 'r') as f:
    cookie = f.read()
