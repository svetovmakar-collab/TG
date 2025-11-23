#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram bot для запуска стиральных машин
"""

import asyncio
import logging
from datetime import datetime
import sys
import socket
import httpx
import os

# Исправление для Windows - ДО импорта aiogram!
# Не меняем event loop policy, оставляем как есть

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import pymysql

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Константы (используем переменные окружения для Railway)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', "8202901943:AAHdB02TlUnUKMulp6moXaZWeBQRz6mSfa8")
DATABASE_CONFIG = {
    'host': os.getenv('DB_HOST', 'manikogaco.beget.app'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'user': os.getenv('DB_USER', 'default-db'),
    'password': os.getenv('DB_PASSWORD', 'Laundry2024!DB'),
    'database': os.getenv('DB_NAME', 'default-db'),
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# Инициализация бота
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния FSM
class MachineLaunch(StatesGroup):
    waiting_city = State()
    waiting_shop = State()
    waiting_machine = State()


def get_db_connection():
    """Получить соединение с БД"""
    try:
        connection = pymysql.connect(**DATABASE_CONFIG)
        return connection
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None


@dp.message(Command('ip'))
async def cmd_ip(message: types.Message):
    """Получить локальный IP адрес"""
    try:
        # Получаем локальный IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        await message.answer(f"📍 Ваш локальный IP: {local_ip}")
    except Exception as e:
        logger.error(f"Error getting IP: {e}")
        await message.answer(f"❌ Ошибка получения IP: {str(e)}")

@dp.message(Command('test'))
async def cmd_test(message: types.Message):
    """Тест подключения к серверу"""
    test_url = "https://screamingly-usable-gunnel.cloudpub.ru/"
    try:
        logger.info(f"Testing connection to {test_url}")
        # Используем local_address для принудительного выбора локального интерфейса
        timeout = httpx.Timeout(10.0, connect=5.0)
        limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
        async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
            resp = await client.get(test_url)
            response_text = resp.text
            logger.info(f"Connection successful: status={resp.status_code}, response={response_text}")
            await message.answer(f"✅ Сервер доступен!\nURL: {test_url}\nСтатус: {resp.status_code}\nОтвет: {response_text}")
    except Exception as e:
        logger.error(f"Test connection error: {type(e).__name__}: {e}")
        await message.answer(f"❌ Ошибка подключения: {type(e).__name__}: {str(e)}")

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    
    # Получаем список городов
    connection = get_db_connection()
    if not connection:
        await message.answer("❌ Ошибка подключения к базе данных")
        return
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM city ORDER BY name ASC")
            cities = cursor.fetchall()
        
        if not cities:
            await message.answer("❌ Города не найдены")
            return
        
        # Создаем инлайн-кнопки с городами
        keyboard = []
        for city in cities:
            keyboard.append([
                InlineKeyboardButton(
                    text=city['name'],
                    callback_data=f"city_{city['id']}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await message.answer("🏙️ Выберите город:", reply_markup=reply_markup)
        await state.set_state(MachineLaunch.waiting_city)
        
    except Exception as e:
        logger.error(f"Error getting cities: {e}")
        await message.answer("❌ Ошибка при загрузке городов")
    finally:
        connection.close()


@dp.callback_query(lambda c: c.data.startswith('city_'), MachineLaunch.waiting_city)
async def process_city(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора города"""
    await callback.answer()
    
    city_id = int(callback.data.split('_')[1])
    await state.update_data(city_id=city_id)
    
    # Получаем список магазинов в этом городе
    connection = get_db_connection()
    if not connection:
        try:
            await callback.message.edit_text("❌ Ошибка подключения к базе данных")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"Error editing message: {e}")
        return
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM shop WHERE city_id = %s ORDER BY name ASC", (city_id,))
            shops = cursor.fetchall()
        
        if not shops:
            try:
                await callback.message.edit_text("❌ Магазины не найдены в этом городе")
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.error(f"Error editing message: {e}")
            return
        
        # Создаем инлайн-кнопки с магазинами
        keyboard = []
        for shop in shops:
            keyboard.append([
                InlineKeyboardButton(
                    text=shop['name'],
                    callback_data=f"shop_{shop['id']}"
                )
            ])
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text("🏪 Выберите точку:", reply_markup=reply_markup)
        await state.set_state(MachineLaunch.waiting_shop)
        
    except Exception as e:
        logger.error(f"Error getting shops: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке магазинов")
    finally:
        connection.close()


@dp.callback_query(lambda c: c.data.startswith('shop_'), MachineLaunch.waiting_shop)
async def process_shop(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора магазина"""
    await callback.answer()
    
    shop_id = int(callback.data.split('_')[1])
    
    # Получаем информацию о магазине и его terminal_url
    connection = get_db_connection()
    if not connection:
        try:
            await callback.message.edit_text("❌ Ошибка подключения к базе данных")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"Error editing message: {e}")
        return
    
    try:
        with connection.cursor() as cursor:
            # Получаем terminal_url магазина
            cursor.execute(
                "SELECT terminal_url FROM shop WHERE id = %s",
                (shop_id,)
            )
            shop = cursor.fetchone()
            
            terminal_url = shop.get('terminal_url') if shop else None
            
            if not terminal_url:
                try:
                    await callback.message.edit_text("❌ Для этого магазина не настроен URL терминала")
                except Exception as e:
                    if "message is not modified" not in str(e).lower():
                        logger.error(f"Error editing message: {e}")
                return
            
            await state.update_data(shop_id=shop_id, terminal_url=terminal_url)
            
            # Получаем список машинок в этом магазине
            cursor.execute(
                "SELECT id, name, kg, machine_number FROM washing_machine WHERE shop_id = %s ORDER BY machine_number ASC",
                (shop_id,)
            )
            machines = cursor.fetchall()
        
        if not machines:
            try:
                await callback.message.edit_text("❌ Машинки не найдены в этом магазине")
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    logger.error(f"Error editing message: {e}")
            return
        
        # Создаем инлайн-кнопки с машинками
        keyboard = []
        row = []
        for i, machine in enumerate(machines):
            machine_name = f"машина {machine['machine_number'] or machine['id']}"
            row.append(
                InlineKeyboardButton(
                    text=machine_name,
                    callback_data=f"machine_{machine['id']}"
                )
            )
            # По 2 кнопки в ряд
            if len(row) == 2 or i == len(machines) - 1:
                keyboard.append(row)
                row = []
        
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await callback.message.edit_text("🔧 Выберите стиральную машину:", reply_markup=reply_markup)
        await state.set_state(MachineLaunch.waiting_machine)
        
    except Exception as e:
        logger.error(f"Error getting machines: {e}")
        await callback.message.edit_text("❌ Ошибка при загрузке машинок")
    finally:
        connection.close()


@dp.callback_query(lambda c: c.data.startswith('machine_'), MachineLaunch.waiting_machine)
async def process_machine(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора машинки"""
    await callback.answer()
    
    machine_id = int(callback.data.split('_')[1])
    data = await state.get_data()
    terminal_url = data.get('terminal_url')  # Получаем URL терминала из состояния
    
    logger.info(f"Machine ID: {machine_id}, Terminal URL: {terminal_url}")
    
    if not terminal_url:
        logger.error("No terminal_url in FSM state")
        try:
            await callback.message.edit_text("❌ URL терминала не найден")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"Error editing message: {e}")
        await state.clear()
        return
    
    # Получаем информацию о машинке
    connection = get_db_connection()
    if not connection:
        try:
            await callback.message.edit_text("❌ Ошибка подключения к базе данных")
        except Exception as e:
            if "message is not modified" not in str(e).lower():
                logger.error(f"Error editing message: {e}")
        return
    
    try:
        with connection.cursor() as cursor:
            # Получаем машинку
            cursor.execute(
                "SELECT * FROM washing_machine WHERE id = %s",
                (machine_id,)
            )
            machine = cursor.fetchone()
            
            if not machine:
                try:
                    await callback.message.edit_text("❌ Машинка не найдена")
                except Exception as e:
                    if "message is not modified" not in str(e).lower():
                        logger.error(f"Error editing message: {e}")
                return
            
            # Получаем номер контроллера
            controller_number = machine['controller_number'] or machine['id']
            
            # Запускаем машинку через API терминала
            try:
                # Нормализуем URL: убираем конечный слеш если он есть
                base_url = terminal_url.rstrip('/')
                nn = f"{controller_number:02d}"  # Форматируем как 01, 02, 03...
                url_on = f"{base_url}/api/washing-machines/send-raw"
                url_off = f"{base_url}/api/washing-machines/send-raw"
                command_on = f"lock{nn}=1"
                command_off = f"lock{nn}=0"
                
                logger.info(f"Sending to: {url_on}, command: {command_on}")
                
                # Таймаут для HTTP-запросов: 30 секунд
                timeout = httpx.Timeout(30.0, connect=5.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    # Импульс: lockNN=1 -> 1000ms -> lockNN=0
                    resp_on = await client.post(url_on, json={"command": command_on})
                    response_on_text = resp_on.text
                    logger.info(f"Response ON: status={resp_on.status_code}, text={response_on_text}")
                    if resp_on.status_code != 200:
                        raise Exception(f"Failed to turn on lock{nn}: status={resp_on.status_code}, text={response_on_text}")
                    
                    # Ждем 1 секунду
                    await asyncio.sleep(1)
                    
                    logger.info(f"Sending to: {url_off}, command: {command_off}")
                    resp_off = await client.post(url_off, json={"command": command_off})
                    response_off_text = resp_off.text
                    logger.info(f"Response OFF: status={resp_off.status_code}, text={response_off_text}")
                    if resp_off.status_code != 200:
                        raise Exception(f"Failed to turn off lock{nn}: status={resp_off.status_code}, text={response_off_text}")
                
                # Успешный запуск
                try:
                    await callback.message.edit_text(
                        f"✅ Машинка №{machine['machine_number'] or machine['id']} запущена!\n"
                        f"📦 Вес: {machine['kg']} кг\n"
                        f"🧼 Количество стирок: {machine['count_washes']}"
                    )
                except Exception as edit_err:
                    # Игнорируем ошибку "message is not modified" - это не критично
                    if "message is not modified" not in str(edit_err).lower():
                        logger.error(f"Error editing message: {edit_err}")
                
            except Exception as api_err:
                logger.error(f"API error: {api_err}")
                try:
                    await callback.message.edit_text(
                        f"❌ Ошибка при запуске машинки\n"
                        f"Проверьте, что терминал доступен: {terminal_url}"
                    )
                except Exception as edit_err:
                    # Игнорируем ошибку "message is not modified" - это не критично
                    if "message is not modified" not in str(edit_err).lower():
                        logger.error(f"Error editing error message: {edit_err}")
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error processing machine: {e}")
        try:
            await callback.message.edit_text("❌ Ошибка при запуске машинки")
        except Exception as edit_err:
            # Игнорируем ошибку "message is not modified" - это не критично
            if "message is not modified" not in str(edit_err).lower():
                logger.error(f"Error editing error message: {edit_err}")
    finally:
        connection.close()


async def main():
    """Главная функция"""
    logger.info("Starting Telegram bot...")
    
    # Запускаем поллинг
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)

