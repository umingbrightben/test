import json
import httpx
import logging
import requests

from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def send_async_restful(url, req_type='get', payload=None, header=None, time_out=40):
    logger.debug('Payload: %s' % payload)
    logger.debug('Send to %s' % url)
    async with httpx.AsyncClient() as client:
        try:
            req_type = req_type.lower()
            method_list = ['get', 'post', 'put', 'delete']
            if req_type not in method_list:
                logger.error(f'Send restful type error, Send to {url!r}, Request type: {req_type}')
                raise HTTPException(status_code=400, detail='Send restful type error.')
            else:
                if req_type == 'get':
                    res = await client.get(url, headers=header, timeout=time_out)
                elif req_type == 'post':
                    res = await client.post(url, json=payload, headers=header, timeout=time_out)
                elif req_type == 'put':
                    res = await client.put(url, json=payload, headers=header, timeout=time_out)
                elif req_type == 'delete':
                    res = await client.delete(url, headers=header, timeout=time_out)
                res.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.error(f'Send restful timeout, Send to {exc.request.url!r}, Request type: {req_type}')
            logger.error(f'Timeout: {time_out}')
            logger.error(f'Detail - {exc!r}')
            if payload is not None:
                logger.error('Error data:')
                logger.error(payload)
            raise HTTPException(status_code=400, detail='Send restful timeout.')
        except httpx.ConnectError as exc:
            logger.error(f'HTTP connection error, Send to {exc.request.url!r}, Request type: {req_type}')
            logger.error(f'Detail - {exc!r}')
            raise HTTPException(status_code=400, detail='Http Connection Error')
        except httpx.RequestError as exc:
            logger.error(f"An error occurred while requesting {exc.request.url!r}.")
            if payload is not None:
                logger.error('Error data:')
                logger.error(payload)
            raise HTTPException(status_code=400, detail='Http Request Error')
        except httpx.HTTPStatusError as exc:
            logger.error(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}.")
            if payload is not None:
                logger.error('Error data:')
                logger.error(payload)
            raise HTTPException(status_code=400, detail='Http Status Error')
        logger.debug('Response code: %d' % res.status_code)
        logger.debug('Response text: %s' % res.text)
        if res.status_code < 210:
            try:
                return res.json(), res.status_code
            except json.decoder.JSONDecodeError:
                return res.text, res.status_code
        else:
            return "", res.status_code


def send_restful(url, req_type='get', payload=None, header=None, time_out=40):
    logger.debug(f'Payload: {payload}')
    logger.debug(f'Send to {url!r}')
    try:
        req_type = req_type.lower()
        method_list = ['get', 'post', 'put', 'delete']
        if req_type not in method_list:
            logger.error(f'Send restful type error, Send to {url!r}, Request type: {req_type}')
            raise HTTPException(status_code=400, detail='Send restful type error.')
        if req_type == 'get':
            res = requests.get(url, headers=header, timeout=time_out)
        elif req_type == 'post':
            res = requests.post(url, json=payload, headers=header, timeout=time_out)
        elif req_type == 'put':
            res = requests.put(url, json=payload, headers=header, timeout=time_out)
        elif req_type == 'delete':
            res = requests.delete(url, json=payload, headers=header, timeout=time_out)
    except requests.exceptions.Timeout as exc:
        logger.error(f'Send restful timeout, Send to {exc.request.url!r}, Request type: {req_type}')
        logger.error(f'Timeout: {time_out}')
        logger.error(f'Detail - {exc!r}')
        if payload is not None:
            logger.error('Error data:')
            logger.error(payload)
        raise HTTPException(status_code=400, detail='Send restful timeout.')
    except requests.exceptions.ConnectionError as exc:
        logger.error(f'HTTP connection error, Send to {exc.request.url!r}, Request type: {req_type}')
        logger.error(f'Detail - {exc!r}')
        raise HTTPException(status_code=400, detail='Http Connection Error')
    logger.debug(f'Response code: {res.status_code}')
    logger.debug(f'Response text: {res.text}')
    if res.status_code < 210:
        try:
            return res.json(), res.status_code
        except json.decoder.JSONDecodeError:
            return res.text, res.status_code
    else:
        return "", res.status_code
