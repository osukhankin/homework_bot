import logging
import os
import sys
import time

import requests
import telegram
from dotenv import load_dotenv

from exceptions import EndpointFailureResponseCodes, InvalidTokens, \
    ResponseFormatFailure, WrongStatusInResponse


# logging.basicConfig(level=logging.DEBUG)
load_dotenv()
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
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
)
handler.setFormatter(formatter)


def check_tokens():
    """Environment variables validation."""
    if None in [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]:
        logger.critical('Please check variables are configured in .env')
        raise InvalidTokens('Please check variables are configured in .env')


def send_message(bot, message):
    """Send status update."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
    except Exception as error:
        logger.error(f'Failure of telegram send_message with error{error}')
    else:
        logger.debug(
            f'Message \"{message}\" was sent from bot to chat '
            f'{TELEGRAM_CHAT_ID}')


def get_api_answer(timestamp):
    """Yandex API answer retrieval function."""
    payload = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(ENDPOINT, headers=HEADERS,
                                         params=payload)
        if homework_statuses.status_code != 200:
            logger.error(
                f'Please check why API response = '
                f'{homework_statuses.status_code}')
            raise EndpointFailureResponseCodes(
                f'Please check why API response = '
                f'{homework_statuses.status_code}')
    except requests.RequestException as error:
        logger.error(error)
    else:
        return homework_statuses.json()


def check_response(response):
    """API response validation based on documentation."""
    if not isinstance(response, dict):
        logger.error('Response data format is not dictionary')
        raise TypeError('Response data format is not dictionary')
    if 'homeworks' not in response.keys():
        logger.error('Please check homeworks existence in response')
        raise ResponseFormatFailure(
            'Please check homeworks existence in response')
    if 'current_date' not in response.keys():
        logger.error('Please check current_date existence in response')
        raise ResponseFormatFailure(
            'Please check current_date existence in response')
    if not isinstance(response['homeworks'], list):
        logger.error('Homeworks data format is not list')
        raise TypeError('Response data format is not list')


def parse_status(homework):
    """Check homework status from API response."""
    if homework['status'] not in HOMEWORK_VERDICTS.keys():
        logger.error('Please validate status in response is based on '
                     'yandex documentation')
        raise WrongStatusInResponse(
            'Please validate status in response is based on '
            'yandex documentation')
    if 'homework_name' not in homework.keys():
        logger.error('Please validate homework_name exist in response')
        raise ResponseFormatFailure(
            'Please validate homework_name exist in response')
    homework_name = homework['homework_name']
    verdict = HOMEWORK_VERDICTS[homework['status']]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Yandex-practicum homework status changes telegram notification."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time()) - LAST_DAY_OFFSET
    new_status = ''
    new_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            check_response(response)
            if len(response['homeworks']) != 0:
                status = parse_status(response['homeworks'][0])
                if new_status != status:
                    new_status = status
                    send_message(bot, status)
            logger.debug('Now status updates yet in your homework')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'

            logger.error(message)
            if new_message != message:
                new_message = message
                send_message(bot, new_message)
        finally:
            if 'Ура!' in new_status:
                break
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
