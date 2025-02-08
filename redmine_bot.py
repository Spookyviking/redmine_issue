import os
import asyncio
import requests
import logging
from datetime import datetime
from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Загрузка конфигурации из переменных окружения
REDMINE_URL = os.getenv("REDMINE_URL_ENV")  # URL Redmine
REDMINE_API_KEY = os.getenv("REDMINE_API_KEY_ENV")  # API-ключ Redmine
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN_ENV")  # Токен Telegram-бота
TELEGRAM_CHAT_ID_SSB = os.getenv("TELEGRAM_CHAT_ID_SSB_ENV")  # ID чата для заявок SSB
TELEGRAM_CHAT_ID_OTHER = os.getenv("TELEGRAM_CHAT_ID_OTHER_ENV")  # ID чата для остальных заявок
PROJECT_ID = os.getenv("REDMINE_PROJECT_ID_ENV")  # Идентификатор проекта в Redmine

# Проверка наличия обязательных переменных
if not all([REDMINE_URL, REDMINE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_SSB, TELEGRAM_CHAT_ID_OTHER, PROJECT_ID]):
    logger.error("Не указаны обязательные переменные окружения: REDMINE_URL, REDMINE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID_SSB, TELEGRAM_CHAT_ID_OTHER, PROJECT_ID")
    exit(1)

# Инициализация бота
bot = Bot(token=TELEGRAM_BOT_TOKEN)

async def get_last_issue_updates():
    """
    Асинхронно получает последние изменения по всем заявкам в проекте.
    Возвращает словарь с ID заявок и их последними временными метками изменений.
    """
    url = f"{REDMINE_URL}/issues.json"
    headers = {
        "X-Redmine-API-Key": REDMINE_API_KEY
    }
    params = {
        "project_id": PROJECT_ID,
        "include": "journals"
    }
    try:
        logger.info(f"Запрос к Redmine API: {url} с параметрами {params}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()  # Проверка на ошибки HTTP
        issues = response.json().get("issues", [])
        logger.info(f"Получены данные: {issues}")
        updates = {}
        for issue in issues:
            issue_id = issue["id"]
            updated_on = issue["updated_on"]
            updates[issue_id] = updated_on
        return updates
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к Redmine API: {e}")
        return {}

async def check_for_updates(last_updates):
    """
    Асинхронно проверяет, есть ли новые заявки или изменения в существующих.
    Возвращает список заявок с изменениями и обновленный словарь last_updates.
    """
    url = f"{REDMINE_URL}/issues.json"
    headers = {
        "X-Redmine-API-Key": REDMINE_API_KEY
    }
    params = {
        "project_id": PROJECT_ID,
        "include": "journals"
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        issues = response.json().get("issues", [])
        updated_issues = []
        for issue in issues:
            issue_id = issue["id"]
            updated_on = issue["updated_on"]
            if issue_id not in last_updates:
                # Новая заявка
                updated_issues.append({"issue": issue, "type": "new"})
                last_updates[issue_id] = updated_on
            elif updated_on > last_updates[issue_id]:
                # Изменение в существующей заявке
                updated_issues.append({"issue": issue, "type": "update"})
                last_updates[issue_id] = updated_on
        return updated_issues, last_updates
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к Redmine API: {e}")
        return [], last_updates

async def send_notification(issue_data):
    """
    Асинхронно отправляет уведомление в Telegram.
    issue_data: словарь с данными о заявке и типом события ("new" или "update").
    """
    try:
        issue = issue_data["issue"]
        event_type = issue_data["type"]
        issue_id = issue["id"]
        subject = issue["subject"]
        priority = issue.get("priority", {}).get("name", "Не указан")  # Приоритет заявки
        assigned_to = issue.get("assigned_to", {}).get("name", "Не назначен")  # Назначенный пользователь
        status = issue.get("status", {}).get("name", "Неизвестен")  # Статус заявки
        created_on = issue.get("created_on", "Неизвестно")  # Дата и время создания заявки
        due_date = issue.get("due_date")  # Дедлайн заявки (может быть None)

        # Форматируем дату и время создания заявки
        if created_on != "Неизвестно":
            created_on_dt = datetime.strptime(created_on, "%Y-%m-%dT%H:%M:%SZ")
            created_on = created_on_dt.strftime("%d.%m.%Y %H:%M")

        # Форматируем due_date, если он указан
        if due_date:
            try:
                due_date_dt = datetime.strptime(due_date, "%Y-%m-%dT%H:%M")
            except ValueError:
                due_date_dt = datetime.strptime(due_date + "T00:00", "%Y-%m-%dT%H:%M")
            due_date = due_date_dt.strftime("%d.%m.%Y %H:%M")
        else:
            due_date = None  # Если дедлайн не указан

        journals = issue.get("journals", [])

        # Логируем значение assigned_to для отладки
        logger.info(f"Заявка #{issue_id}: назначена на '{assigned_to}'")

        # Определяем, в какой чат отправлять уведомление
        if "ССБ ССБ" in assigned_to:  # Проверяем, содержит ли assigned_to строку "SSB"
            chat_id = TELEGRAM_CHAT_ID_SSB
        else:
            chat_id = TELEGRAM_CHAT_ID_OTHER

        # Формируем сообщение в зависимости от типа события
        if event_type == "new":
            message = (
                f"🆕 Новая заявка #{issue_id}:\n"
                f"📝 Тема: {subject}\n"
                f"🚩 Приоритет: {priority}\n"
                f"👤 Назначена: {assigned_to}\n"
                f"📊 Статус: {status}\n"
                f"📅 Создана: {created_on}\n"
            )
            if due_date:  # Добавляем дедлайн, если он указан
                message += f"⏳ Дедлайн: {due_date}\n"
            message += f"🔗 Ссылка: {REDMINE_URL}/issues/{issue_id}"
        elif event_type == "update":
            if journals:
                last_journal = journals[-1]
                user = last_journal.get("user", {}).get("name", "Неизвестный пользователь")
                notes = last_journal.get("notes", "Без описания")
                message = (
                    f"🔄 Изменение в заявке #{issue_id}:\n"
                    f"📝 Тема: {subject}\n"
                    f"🚩 Приоритет: {priority}\n"
                    f"👤 Назначена: {assigned_to}\n"
                    f"📊 Статус: {status}\n"
                    f"📅 Создана: {created_on}\n"
                )
                if due_date:  # Добавляем дедлайн, если он указан
                    message += f"⏳ Дедлайн: {due_date}\n"
                message += (
                    f"👤 Пользователь: {user}\n"
                    f"📄 Примечание: {notes}\n"
                    f"🔗 Ссылка: {REDMINE_URL}/issues/{issue_id}"
                )
            else:
                message = (
                    f"🔄 Изменение в заявке #{issue_id}:\n"
                    f"📝 Тема: {subject}\n"
                    f"🚩 Приоритет: {priority}\n"
                    f"👤 Назначена: {assigned_to}\n"
                    f"📊 Статус: {status}\n"
                    f"📅 Создана: {created_on}\n"
                )
                if due_date:  # Добавляем дедлайн, если он указан
                    message += f"⏳ Дедлайн: {due_date}\n"
                message += f"🔗 Ссылка: {REDMINE_URL}/issues/{issue_id}"
        else:
            logger.warning(f"Неизвестный тип события: {event_type}")
            return

        await bot.send_message(chat_id=chat_id, text=message)
        logger.info(f"Уведомление отправлено в чат {chat_id}: {message}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления: {e}")

async def main():
    """
    Основная асинхронная функция, которая запускает мониторинг заявок.
    """
    last_updates = await get_last_issue_updates()  # Получаем последние изменения при старте
    while True:
        updated_issues, last_updates = await check_for_updates(last_updates)
        for issue_data in updated_issues:
            await send_notification(issue_data)
        await asyncio.sleep(10)  # Проверка каждые n-секунд

if __name__ == "__main__":
    # Запуск асинхронного цикла
    asyncio.run(main())