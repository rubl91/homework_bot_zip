import logging
import sys
import requests
import telegram
import time

from http import HTTPStatus

from os import getenv

from dotenv import load_dotenv

from exceptions import EmptyDictInResponseError, JSONError, StatusCodeError

load_dotenv()

PRACTICUM_TOKEN = getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(stream=sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s, [%(levelname)s] %(message)s'
)
handler.setFormatter(formatter)


def send_message(bot, message):
    """
    Отсылает сообщение в Telegram чат.
    Принимает на вход два параметра: экземпляр класса
    Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Успешная отправка сообщения  %s', message)
    except Exception as error:
        logger.error('Сбой при отправке сообщения %s', error)


def get_api_answer(current_timestamp):
    """
    Запрос к единственному эндпоинту API-сервиса.
    В качестве параметра параметра функция получает временную метку.
    В случае успешного запроса должна вернуть ответ API, преобразовав
    его из формата JSON к типам данных Python.
    """
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
    """
    Проверка ответа API на корректность.
    В качестве параметра функция получает ответ API, приведенный к типам
    данных Python. Если ответ API соответствует ожиданиям, то функция
    должна вернуть список домашних работ (он может быть и пустым),
    доступный в ответе API по ключу 'homeworks'.
    """
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
    """
    Извлекает из информации о конкретной домашней работе статус работы.
    В качестве параметра функция получает только один элемент из списка
    домашних работ. В случае успеха, функция возвращает подготовленную для
    отправки в Telegram строку, содержащую один из вердиктов словаря
    HOMEWORK_VERDICTS.
    """
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    verdict = HOMEWORK_VERDICTS.get(homework_status)
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
    """Проверка доступности переменных окружения."""
    return all((PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID))


def main():
    """Основная логика работы бота."""
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
            logger.info('Переход в режим ожидания: %d с', RETRY_PERIOD)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
