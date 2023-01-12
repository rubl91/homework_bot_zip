from http import HTTPStatus
import logging
import sys
import requests
import telegram
import time

from os import getenv

from dotenv import load_dotenv

from exceptions import EmptyDictInResponseError, JSONError, StatusCodeError

load_dotenv()


PRACTICUM_TOKEN = getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена, замечаний нет',
    'reviewing': 'Работа проверяется',
    'rejected': 'Работа проверена, есть замечания'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s, [%(levelname)s] %(message)s'
)
handler.setFormatter(formatter)


def send_message(bot, message):
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info('Успешная отправка сообщения  %s', message)
    except Exception as error:
        logger.error('Сбой при отправке сообщения %s', error)


def get_api_answer(current_timestamp):
    logger.info('Начало запроса к API')
    timestamp = current_timestamp
    params = {'from_date': timestamp}
    try:
        homeworks = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.ConnectionError as error:
        logger.error('Произошла ошибка подключения: %s', error)
    except requests.URLRequired as error:
        logger.error('Ошибка в URL-адресе "%s": %s', homeworks.url, error)
    except Exception as error:
        logger.error('Ошибка при запросе к API Практикум.Домашка: %s', error)
    if homeworks.status_code != HTTPStatus.OK:
        raise StatusCodeError(
            f'Код HTTP ответа при запросе к API - {homeworks.status_code}'
            f' Headers при запросе к API - "{homeworks.headers}"'
        )
    try:
        homeworks_json = homeworks.json()
    except Exception as error:
        raise JSONError(
            (
                'Ошибка при преобразовании ответа из'
                f' JSON к типам данных Python: {error}'
            )
        )
    else:
        logger.info('Запроса к API осуществлен успешно')
        return homeworks_json


def check_response(response):
    logger.info('Проверка ответа API на корректность')
    if not response:
        raise EmptyDictInResponseError('Ответ от API содержит пустой словарь')
    if not isinstance(response, dict):
        raise TypeError('Ответ от API не является словарем')
    if response.get('current_date') is None:
        raise KeyError('Ответ от API не содержит ключ "current_date"')
    homeworks = response.get('homeworks')
    if homeworks is None:
        raise KeyError('Ответ от API не содержит ключ "homeworks"')
    if not isinstance(homeworks, list):
        raise TypeError(
            'Данные в ответе API по ключу "homeworks" не являются словарем'
        )
    logger.info('Ответ API корректен')
    return homeworks


def parse_status(homework):
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    verdict = HOMEWORK_STATUSES.get(homework_status)
    if homework_name is None:
        raise KeyError(
            'Словарь с домашней работой не содержит ключ "homework_name"'
        )
    if homework_status is None:
        raise KeyError(
            'Словарь с домашней работой не содержит ключ "status"'
        )
    if verdict is None:
        raise KeyError('Недокументированный статус домашней работы')
    logger.info('Статус проверки работы получен')
    return (
        f'Изменился статус проверки работы "{homework_name}". {verdict}'
    )


def check_tokens():
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())
    if not check_tokens():
        message = 'Отсутвует (нет доступа) к переменной окружения'
        logger.critical(message)
        send_message(bot, message)
        sys.exit(message)
    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('В ответе отстутвуют новые статусы проверки')
        except Exception as error:
            logger.error(error)
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
        finally:
            logger.info('Переход в режим ожидания: %d с', RETRY_TIME)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
