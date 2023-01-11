import logging
import os
import requests
import telegram
import time

from dotenv import load_dotenv
from exceptions import ParseStatusError
from http import HTTPStatus
from logging import StreamHandler
from typing import Union

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности переменных окружения."""
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправка сообщения в Telegram чат с TELEGRAM_CHAT_ID.

    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Бот отправил сообщение. {message}')
    except Exception as error:
        logger.error(error)


def get_api_answer(current_timestamp: int) -> Union[dict, str]:
    """Запрос к единственному эндпоинту API-сервиса.

    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна вернуть ответ API,
    приведя его из формата JSON к типам данных Python.
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(ENDPOINT,
                                         headers=HEADERS,
                                         params=params
                                         )
    except Exception as error:
        logger.error(f'Ошибка при запросе к основному API: {error}')
        raise Exception(f'Ошибка при запросе к основному API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        status_code = homework_statuses.status_code
        logger.error(f'Ошибка {status_code}')
        raise Exception(f'Ошибка {status_code}')
    try:
        return homework_statuses.json()
    except ValueError:
        logger.error('Ошибка парсинга ответа из формата json')
        raise ValueError('Ошибка парсинга ответа из формата json')


def check_response(response):
    """Проверка ответа API на соответствие документации.

    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if not isinstance(response, dict):
        message = 'Некорректный тип'
        logger.error(message)
        raise TypeError(message)
    if 'homeworks' not in response:
        message = 'Отсутствуют ожидаемые ключи в ответе'
        logger.error(message)
        raise KeyError(message)
    if not isinstance(response.get('homeworks'), list):
        message = 'Формат ответа не соответствует'
        logger.error(message)
        raise TypeError(message)
    return response['homeworks']


def parse_status(homework: dict) -> str:
    """Извлечение статуса домашней работы.

    В качестве параметра функция получает только
    один элемент из списка домашних работ.
    В случае успеха, функция возвращает подготовленную
    для отправки в Telegram строку,
    содержащую один из вердиктов словаря HOMEWORK_VERDICTS.
    """
    if not homework.get('homework_name'):
        homework_name = 'NoName'
        message = 'Отсутствует имя домашней работы'
        logger.warning(message)
        raise KeyError(message)
    else:
        homework_name = homework.get('homework_name')

    homework_status = homework.get('status')

    if 'status' not in homework:
        message = 'Отсутствует ключ homework_status'
        logger.error(message)
        raise ParseStatusError(message)

    verdict = HOMEWORK_VERDICTS.get(homework_status)

    if homework_status not in HOMEWORK_VERDICTS:
        message = 'Недокументированный статус домашней работы'
        logger.error(message)
        raise KeyError(message)

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    last_send = {
        'error': None,
    }
    if not check_tokens():
        logger.critical('Отсутствует переменная окружения')
        exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if len(homeworks) == 0:
                logger.debug('Ответ API пуст. Домашних работ нет')
                break
            for homework in homeworks:
                message = parse_status(homework)
                if last_send.get(homework['homework_name']) != message:
                    send_message(bot, message)
                    last_send[homework['homework_name']] = message
            current_timestamp = response.get('current_date')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if last_send['error'] != message:
                send_message(bot, message)
                last_send['error'] = message
        else:
            last_send['error'] = None
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = StreamHandler()
    logger.addHandler(handler)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    handler.setFormatter(formatter)

    main()
