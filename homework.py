import http
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import requests
import telegram
from dotenv import load_dotenv

from exceptions import (EndpointFailureResponseCodes, InvalidTokens,
                        ResponseFormatFailure, WrongStatusInResponse)


load_dotenv()
BASE_DIR = os.path.dirname(__file__)
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
LAST_DAY_OFFSET = 86400
HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stream=sys.stdout)
file_handler = RotatingFileHandler(
    os.path.join(BASE_DIR, 'logs', 'homework_bot.log'), maxBytes=1000000,
    backupCount=5)
logger.addHandler(handler)
logger.addHandler(file_handler)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] [%(filename)s]:[%(lineno)s] [%(funcName)s] '
    '%(message)s '
)
handler.setFormatter(formatter)
file_handler.setFormatter(formatter)


def check_tokens():
    """Environment variables validation."""
    env_vars = (
        ('PRACTICUM_TOKEN', PRACTICUM_TOKEN),
        ('TELEGRAM_TOKEN', TELEGRAM_TOKEN),
        ('TELEGRAM_CHAT_ID', TELEGRAM_CHAT_ID),
    )
    temp_bool = True
    for name, value in env_vars:
        if value is None:
            logger.critical(f'Пожалуйста, укажите переменную {name} в .env')
            temp_bool = False
    return temp_bool


def send_message(bot, message):
    """Send status update."""
    logger.debug('Попытка отправить сообщение в чат бота')
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except telegram.error.TelegramError as error:
        logger.error(f'Ошибка отправки сообщения в чат бота - {error}')
        return False
    else:
        logger.debug(
            f'Message \"{message}\" was sent from bot to chat '
            f'{TELEGRAM_CHAT_ID}')
        return True


def get_api_answer(timestamp):
    """Yandex API answer retrieval function."""
    # payload = {'from_date': timestamp}
    url_params = {
        'EP': ENDPOINT,
        'HD': HEADERS,
        'PL': {'from_date': timestamp},
    }
    logger.debug('Попытка запроса статуса домашней работы: '
                 'URL = {EP}, '
                 'HEADERS = {HD}, '
                 'PAYLOAD = {PL}, '.format(**url_params))
    try:
        homework_statuses = requests.get(url_params['EP'],
                                         headers=url_params['HD'],
                                         params=url_params['PL'])
        if homework_statuses.status_code != http.HTTPStatus.OK:
            raise EndpointFailureResponseCodes(
                f'Please check why API response failed = '
                f'status_code:{homework_statuses.status_code}, '
                f'reason:{homework_statuses.reason}, '
                f'text: {homework_statuses.text}')
        return homework_statuses.json()
    except requests.RequestException as error:
        logger.error(error)
        raise ConnectionError('Ошибка соединения при попыткы запроса '
                              'статуса домашней работы: '
                              'URL = {EP}, '
                              'HEADERS = {HD}, '
                              'PAYLOAD = {PL}, '.format(**url_params))


def check_response(response):
    """API response validation based on documentation."""
    if not isinstance(response, dict):
        raise TypeError('Response data format is not dictionary')
    if 'homeworks' not in response:
        raise ResponseFormatFailure(
            'Please check homeworks existence in response')
    if 'current_date' not in response:
        raise ResponseFormatFailure(
            'Please check current_date existence in response')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise TypeError('Response data format is not list')
    return homeworks


def parse_status(homework):
    """Check homework status from API response."""
    status = homework.get('status')
    if status not in HOMEWORK_VERDICTS:
        logger.error('Проверьте, что присланный статус '
                     'соответствует документации')
        raise WrongStatusInResponse(
            f'Please validate status - "{status}" in response is based on '
            'yandex documentation')
    if 'homework_name' not in homework:
        logger.error('Проверьте, что ключ homework_name приходит в ответе')
        raise ResponseFormatFailure(
            'Please validate homework_name exist in response')
    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Yandex-practicum homework status changes telegram notification."""
    if not check_tokens():
        logger.critical('Пожалуйста, проверьте переменные окружения')
        raise InvalidTokens('Please check variables are configured in .env')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = 0
    current_report = {
        'homework_name': '',
        'message_output': '',
    }
    prev_report = {
        'homework_name': '',
        'message_output': '',
    }

    while True:
        try:
            response = get_api_answer(timestamp)
            homework_name = check_response(response)
            current_report['homework_name'] = homework_name
            if homework_name:
                last_homework_name = homework_name[0]
                current_report['message_output'] = parse_status(
                    last_homework_name)
            else:
                current_report['message_output'] = 'Обновлений нет'
            if (current_report != prev_report
                    and send_message(bot, current_report['message_output'])):
                prev_report = current_report.copy()
                timestamp = response.get('current_date')
            else:
                logger.debug('Обновлений нет')
        except ResponseFormatFailure as error:
            logger.error(error)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            current_report['message_output'] = message
            logger.error(message)
            if (current_report != prev_report
                    and send_message(bot, current_report['message_output'])):
                prev_report = current_report.copy()
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
