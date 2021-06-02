import pymongo
import json


def get_db_info(db_port, db_name):
    db_list = pymongo.MongoClient('mongodb://localhost:' + str(db_port)).list_database_names()
    if db_name not in db_list:
        print(db_name + ' not found')
        return
    db = pymongo.MongoClient('mongodb://localhost:' + str(db_port))[db_name]
    collect_list = db.list_collection_names()
    if 'log' not in collect_list:
        print('log not found')
        return
    logs = db.log.find({}).sort([('finish_time', -1)]).limit(1)
    if not logs[0]:
        print('no log')
        return
    log = logs[0]
    del log['_id']

    stats = db.command('dbstats')
    stats = {
        "collections": stats['collections'],
        "documents": stats['objects'],
        "data_size": stats['dataSize'],
        "index_size": stats['indexSize']
    }

    print(json.dumps(stats))
    print(json.dumps(log))
