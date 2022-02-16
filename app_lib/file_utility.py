import os
import uuid
import logging
import aiofiles

from fastapi import UploadFile, File
from typing import List

from core.devicemgr_config import (FILE_SAVED_FOLDER)


# Setting Logger
LOGGER = logging.getLogger(__name__)


def generate_hex_uuid() -> str:
    """ Create unique uuid for using """
    return uuid.uuid4().hex


async def save_file(file_name: str, in_file: UploadFile = File(...)):
    """ Async saving file in to images folder """
    LOGGER.info(f"Saved image name: {file_name}")

    save_file_path = f"{FILE_SAVED_FOLDER}{file_name}"

    async with aiofiles.open(save_file_path, 'wb') as out_file:
        content = await in_file.read()  # async read
        await out_file.write(content)  # async write

    return


async def delete_file(file_name: str):
    """ Async delete file from images folder """
    LOGGER.info(f"Delete image name: {file_name}")

    delete_file_path = f"{FILE_SAVED_FOLDER}{file_name}"

    if os.path.exists(delete_file_path):
        # File exist and delete
        await aiofiles.os.remove(delete_file_path)
    else:
        LOGGER.warning(f"File Not exist in ({delete_file_path})")
        pass

    return


async def save_files(in_files: List[UploadFile] = File(...)):
    """ Async saving file in to images folder """
    LOGGER.info(f"Save image in {FILE_SAVED_FOLDER}")

    if not os.path.exists(FILE_SAVED_FOLDER):
        os.mkdir(FILE_SAVED_FOLDER)

    res_data = []
    for file in in_files:
        # Split input filename and extention and generate new unique file name with uuid
        new_uuid = generate_hex_uuid()
        _, ext = os.path.splitext(file.filename)
        new_filename = new_uuid + ext
        await save_file(new_filename, file)
        res_data.append(new_filename)

    return res_data
