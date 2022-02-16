import logging

from bson.objectid import ObjectId
from dynaconf import settings
from fastapi import HTTPException

from app_lib.mongo_utility import DataLoader


# Setting Logger
LOGGER = logging.getLogger(__name__)


def update_db_data(db, filter_dict, new_data, functionality: str):
    """ Update data in db with
    filter_dict:
    {
      "key1": value1,
      "key2": value2
    }
    """
    if '_id' in filter_dict:
        filter_dict['_id'] = ObjectId(filter_dict['_id'])
    if db.check_exist_one(filter_dict):
        for key, val in filter_dict.items():
            if key == '_id':
                continue
            elif new_data[key] != val:
                LOGGER.error("Please don't modify filter in new data")
                LOGGER.error(f"Filter key: {key}, Filter values: {val}")
                LOGGER.error(f"New data value: {new_data[key]}")
                raise HTTPException(status_code=400, detail=f"Post data value of key {key} is not same as input value in url.")
        else:
            # After for loop data, update db data by filter dict
            update_data = {"$set": new_data}
            db.update_one(filter_dict, update_data)
        return new_data
    else:
        detail_str = f"Device {functionality}, filter is not exist. Please use POST method. Filter: {filter_dict}"
        LOGGER.error(detail_str)
        raise HTTPException(status_code=400, detail=detail_str)


def get_db_all_data(database: str, collection: str):
    """
    Get db all data
    """
    res_data = []
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'], database, collection)
    res_data = db.get_all_elements()
    return res_data


def get_db_data_by_filter(database: str, collection: str, filter_dict: dict):
    """
    Get db data by filter
    """
    res_data = {}
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'], database, collection)
    if not db.check_exist_one(filter_dict):
        return res_data

    res_data = db.get_one_by_filter(filter_dict)
    return res_data


def write_data_to_mongo(database: str, collection: str, filter_dict: dict, new_data: dict, update_func: str):
    """ Update/Write data from mongo """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'], database, collection)
    LOGGER.debug(f"Update {update_func}: {new_data}")
    if db.check_exist_one(filter_dict):
        LOGGER.warning(f"Data is found, update data. Filter: {filter_dict}")
        _ = update_db_data(db, filter_dict, new_data, update_func)
    else:
        LOGGER.warning(f"Data not found, add new one. Filter: {filter_dict}")
        db.write_one(new_data)
    return


def delete_data_from_mongo(database: str, collection: str, filter_dict: dict, update_func: str):
    """ Delete data from mongo """
    db = DataLoader(settings['MONGO_SERVER']['IP'], settings['MONGO_SERVER']['PORT'], database, collection)
    LOGGER.warning(f"Data ({update_func}) is ready to be deleted. Filter: {filter_dict}")
    db.delete_one_by_filter(filter_dict)
    return
