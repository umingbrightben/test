import logging

from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId

LOGGER = logging.getLogger(__name__)


class DataLoader():
    def __init__(self, mongodb_ip, mongodb_port, mongodb_db, mongodb_col=""):
        self.db_name = mongodb_db
        self.db_col = mongodb_col
        self.client = MongoClient(mongodb_ip, mongodb_port)
        self.db = self.client[self.db_name]
        if self.db_col:
            self.col = self.db[self.db_col]

    def get_all_elements(self):
        cursers = self.col.find()
        res = []
        for data in cursers:
            del data['_id']
            res.append(data)
        return res

    def get_all_elements_with_id(self):
        cursers = self.col.find()
        return list(cursers)

    def get_all_elements_and_sort(self, filter_name, reverse):
        if reverse:
            # From big to small
            res_data = list(self.col.find({}, {'_id': False}).sort(filter_name, -1))
        else:
            res_data = list(self.col.find({}, {'_id': False}).sort(filter_name, 1))
        return res_data

    def get_many_by_name(self, name):
        res = self.col.find({"name": name})
        return list(res)

    def get_many_by_filter(self, filter_dict):
        """ filter ex: {'key1': 'value1', 'key2': 'value2', 'key3': 'value4'} """
        res = self.col.find(filter_dict, {'_id': False})
        return list(res)

    def get_one_by_name(self, name):
        res = self.col.find_one({"name": name}, {'_id': False})
        return res

    def get_one_by_key(self, key, value):
        res = self.col.find_one({key: value}, {'_id': False})
        return res

    def get_one_by_id(self, _id):
        res = self.col.find_one({"_id": _id})
        return res

    def get_one_by_filter(self, filter_dict):
        """ filter ex: {'key1': 'value1', 'key2': 'value2', 'key3': 'value4'} """
        res = self.col.find_one(filter_dict, {'_id': False})
        return res

    def get_collection_name_in_db(self):
        collections = self.db.list_collection_names()
        return collections

    def write_one(self, data):
        self.col.insert(data)

    def update_one(self, filter, data):
        """ filter ex: {'key1': 'value1', 'key2': 'value2', 'key3': 'value4'} """
        self.col.update_one(filter, data)

    def update_many(self, filter, data):
        """ filter ex: {'key1': 'value1', 'key2': 'value2', 'key3': 'value4'} """
        self.col.update_many(filter, data)

    def check_exist_one_by_name(self, name):
        data = self.col.find_one({"name": name})
        if data:
            return True
        return False

    def check_exist_one(self, filter_data):
        data = self.col.find_one(filter_data)
        if data:
            return True
        return False

    def check_exist_one_by_id(self, _id):
        data = self.col.find_one({"_id": ObjectId(_id)})
        if data:
            return True
        return False

    def delete_one_by_name(self, name):
        self.col.delete_one({"name": name})

    def delete_one_by_key(self, key, value):
        self.col.delete_one({key: value})

    def delete_one_by_filter(self, filter):
        """ Delete all matching cursor, input dict sample: {"name": "A", "type": "application"} """
        self.col.delete_one(filter)

    def delete_one_by_id(self, _id):
        try:
            self.col.delete_one({"_id": ObjectId(_id)})
        except InvalidId:
            LOGGER.error(f"({_id}) is not a valid ObjectId, it must be a 12-byte input or a 24-character hex string")
            return False
        return True

    def delete_many_by_filter(self, filter):
        """ Delete all matching cursor, input dict sample: {"name": "A", "type": "application"} """
        self.col.delete_many(filter)

    def delete_collection(self):
        self.col.drop()
