Я подготовлю код для бота VK на Python. Это будет комплексное решение с использованием фреймворка vkbottle (современный асинхронный фреймворк для VK API) и aiogram-подобным подходом.
Python
Copy
"""
Banana Boom VK Bot - AI генерация фото и видео
Архитектура: vkbottle + SQLite + интеграция с API нейросетей
"""

import asyncio
import json
import logging
import sqlite3
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Dict, List, Any
from datetime import datetime
import aiohttp
import os
from pathlib import Path

from vkbottle import Bot, Message, PhotoMessageUploader, DocMessageUploader
from vkbottle.modules import json as json_module
from vkbottle.dispatch.rules.base import CommandRule, PayloadRule

# ==================== КОНФИГУРАЦИЯ ====================

class Config:
    VK_TOKEN = "YOUR_VK_GROUP_TOKEN"  # Токен сообщества VK
    ADMIN_ID = 123456789  # ID администратора для уведомлений
    
    # API ключи для нейросетей (замените на реальные)
    KLING_API_KEY = "your_kling_api_key"
    HAIPE_API_KEY = "your_haiper_api_key"
    SEEDANCE_API_KEY = "your_seedance_api_key"
    VEO_API_KEY = "your_veo_api_key"
    GROK_API_KEY = "your_grok_api_key"
    
    # Базовые цены в "бананах"
    PRICES = {
        "photo_generate": 5,
        "video_kling_3_std": 15,
        "video_kling_3_pro": 15,
        "video_seedance_15": 14,
        "video_seedance_20": 17,
        "video_haiper_23": 18,
        "video_veo_31": 30,
        "video_grok_img2video": 18,
        "motion_control_standard": 10,
        "motion_control_pro": 30,
        "ai_avatar_pro": 10,  # за секунду
        "infinitalk": 10,  # за секунду
        "photo_analysis": 0,  # бесплатно
    }
    
    # Начальный баланс новых пользователей
    STARTING_BALANCE = 10
    
    # Пути
    DB_PATH = "banana_boom.db"
    UPLOAD_DIR = "uploads"
    OUTPUT_DIR = "outputs"

# Создаём директории
Path(Config.UPLOAD_DIR).mkdir(exist_ok=True)
Path(Config.OUTPUT_DIR).mkdir(exist_ok=True)

# ==================== БАЗА ДАННЫХ ====================

class Database:
    def __init__(self, db_path: str = Config.DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Пользователи
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_blocked BOOLEAN DEFAULT 0,
                block_reason TEXT
            )
        """)
        
        # Задачи на генерацию
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generation_tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_type TEXT,
                model TEXT,
                prompt TEXT,
                reference_photos TEXT,  -- JSON список путей
                status TEXT DEFAULT 'pending',  -- pending, processing, completed, failed
                cost INTEGER,
                result_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # История транзакций
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,  -- положительное = пополнение, отрицательное = списание
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Состояния пользователей (для FSM)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT,  -- JSON с дополнительными данными
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    
    # === Методы для пользователей ===
    
    def get_or_create_user(self, user_id: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute(
                "INSERT INTO users (user_id, balance) VALUES (?, ?)",
                (user_id, Config.STARTING_BALANCE)
            )
            conn.commit()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = cursor.fetchone()
        
        conn.close()
        return {
            "user_id": user[0],
            "balance": user[1],
            "created_at": user[2],
            "last_activity": user[3],
            "is_blocked": user[4],
            "block_reason": user[5]
        }
    
    def update_balance(self, user_id: int, amount: int, reason: str) -> bool:
        """Изменить баланс. amount может быть отрицательным для списания."""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Проверяем текущий баланс при списании
        if amount < 0:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            current = cursor.fetchone()
            if not current or current[0] + amount < 0:
                conn.close()
                return False  # Недостаточно средств
        
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)",
            (user_id, amount, reason)
        )
        conn.commit()
        conn.close()
        return True
    
    def get_balance(self, user_id: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    
    # === Методы для состояний (FSM) ===
    
    def set_state(self, user_id: int, state: str, data: dict = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT OR REPLACE INTO user_states (user_id, state, data, updated_at) 
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
            (user_id, state, json.dumps(data or {}))
        )
        conn.commit()
        conn.close()
    
    def get_state(self, user_id: int) -> Optional[tuple]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT state, data FROM user_states WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            return result[0], json.loads(result[1])
        return None, {}
    
    def clear_state(self, user_id: int):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    
    # === Методы для задач ===
    
    def create_task(self, user_id: int, task_type: str, model: str, 
                    prompt: str, cost: int, reference_photos: list = None) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO generation_tasks 
               (user_id, task_type, model, prompt, reference_photos, cost) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, task_type, model, prompt, 
             json.dumps(reference_photos or []), cost)
        )
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id
    
    def update_task_status(self, task_id: int, status: str, 
                          result_url: str = None, error_message: str = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """UPDATE generation_tasks 
               SET status = ?, result_url = ?, error_message = ?, 
                   completed_at = CASE WHEN ? IN ('completed', 'failed') 
                                  THEN CURRENT_TIMESTAMP ELSE NULL END
               WHERE task_id = ?""",
            (status, result_url, error_message, status, task_id)
        )
        conn.commit()
        conn.close()

# ==================== СОСТОЯНИЯ БОТА ====================

class UserState(Enum):
    IDLE = "idle"
    
    # Создание видео
    VIDEO_WAITING_PROMPT = "video_waiting_prompt"
    VIDEO_WAITING_REFERENCES = "video_waiting_references"
    
    # Создание фото
    PHOTO_WAITING_PROMPT = "photo_waiting_prompt"
    PHOTO_WAITING_REFERENCES = "photo_waiting_references"
    
    # Motion Control
    MC_WAITING_CHARACTER_PHOTO = "mc_waiting_character_photo"
    MC_WAITING_MOTION_VIDEO = "mc_waiting_motion_video"
    
    # Анализ фото
    ANALYSIS_WAITING_PHOTO = "analysis_waiting_photo"
    
    # AI Avatar
    AVATAR_WAITING_PHOTO = "avatar_waiting_photo"
    AVATAR_WAITING_AUDIO = "avatar_waiting_audio"

# ==================== API КЛИЕНТЫ ДЛЯ НЕЙРОСЕТЕЙ ====================

class AIAPIClient:
    """Базовый клиент для API нейросетей"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def generate_video_kling(self, prompt: str, image_url: str = None,
                                    model: str = "3.0_std", duration: int = 5) -> str:
        """Генерация через Kling API (заглушка - замените на реальный API)"""
        # TODO: Реальная интеграция с Kling API
        await asyncio.sleep(2)  # Имитация задержки
        return f"https://example.com/kling_result_{model}.mp4"
    
    async def generate_video_haiper(self, prompt: str, image_url: str = None) -> str:
        """Генерация через Haiper API"""
        await asyncio.sleep(2)
        return "https://example.com/haiper_result.mp4"
    
    async def generate_video_seedance(self, prompt: str, image_url: str = None,
                                       version: str = "1.5") -> str:
        """Генерация через Seedance API"""
        await asyncio.sleep(2)
        return f"https://example.com/seedance_{version}_result.mp4"
    
    async def generate_video_veo(self, prompt: str, image_url: str = None) -> str:
        """Генерация через Veo API"""
        await asyncio.sleep(3)
        return "https://example.com/veo_result.mp4"
    
    async def generate_video_grok(self, image_url: str) -> str:
        """Grok Img2Video"""
        await asyncio.sleep(2)
        return "https://example.com/grok_result.mp4"
    
    async def generate_photo(self, prompt: str, references: List[str] = None) -> str:
        """Генерация фото (FLUX/Stable Diffusion)"""
        await asyncio.sleep(2)
        return "https://example.com/photo_result.jpg"
    
    async def analyze_photo(self, photo_url: str) -> str:
        """Анализ фото и создание промпта"""
        # Имитация анализа через GPT-4 Vision или аналог
        await asyncio.sleep(1)
        return f"Детальный промпт на основе анализа: профессиональное фото, освещение сбоку, цветокоррекция теплая..."

# ==================== КЛАВИАТУРЫ ====================

class Keyboards:
    @staticmethod
    def main_menu():
        return {
            "inline": True,
            "buttons": [
                [
                    {"action": {"type": "text", "label": "🎬 Создать видео", "payload": {"cmd": "create_video"}}},
                    {"action": {"type": "text", "label": "🎥 Motion Control", "payload": {"cmd": "motion_control"}}}
                ],
                [
                    {"action": {"type": "text", "label": "🖼 Создать фото", "payload": {"cmd": "create_photo"}}},
                    {"action": {"type": "text", "label": "📸 Фото→Промпт", "payload": {"cmd": "photo_analysis"}}}
                ],
                [
                    {"action": {"type": "text", "label": "💰 Пополнить", "payload": {"cmd": "top_up"}}},
                    {"action": {"type": "text", "label": "🔧 Тех поддержка", "payload": {"cmd": "support"}}}
                ]
            ]
        }
    
    @staticmethod
    def video_models():
        return {
            "inline": True,
            "buttons": [
                [{"action": {"type": "text", "label": "⚡ Kling 3.0 std • 15 🍌", "payload": {"model": "kling_3_std", "cost": 15}}}],
                [{"action": {"type": "text", "label": "💎 Kling 3.0 pro • 15 🍌", "payload": {"model": "kling_3_pro", "cost": 15}}}],
                [{"action": {"type": "text", "label": "🌱 Seedance 1.5 pro • 14 🍌", "payload": {"model": "seedance_15", "cost": 14}}}],
                [{"action": {"type": "text", "label": "🌿 Seedance 2.0 • 17 🍌", "payload": {"model": "seedance_20", "cost": 17}}}],
                [{"action": {"type": "text", "label": "🌊 Хайлуо 2.3 • 18 🍌", "payload": {"model": "haiper_23", "cost": 18}}}],
                [{"action": {"type": "text", "label": "👁 Veo 3.1 • 30 🍌", "payload": {"model": "veo_31", "cost": 30}}}],
                [{"action": {"type": "text", "label": "🤖 Grok Img→Video • 18 🍌", "payload": {"model": "grok_img2video", "cost": 18}}}],
                [{"action": {"type": "text", "label": "🏠 Главное меню", "payload": {"cmd": "main_menu"}}}]
            ]
        }
    
    @staticmethod
    def video_options():
        return {
            "inline": True,
            "buttons": [
                [
                    {"action": {"type": "text", "label": "✅ Текст", "payload": {"input": "text"}}},
                    {"action": {"type": "text", "label": "🖼 Фото + Текст", "payload": {"input": "photo_text"}}},
                    {"action": {"type": "text", "label": "🎬 Видео + Текст", "payload": {"input": "video_text"}}}
                ],
                [{"action": {"type": "text", "label": "⬅️ Назад", "payload": {"cmd": "create_video"}}}]
            ]
        }
    
    @staticmethod
    def aspect_ratios():
        return {
            "inline": True,
            "buttons": [
                [
                    {"action": {"type": "text", "label": "✅ 16:9", "payload": {"ratio": "16:9"}}},
                    {"action": {"type": "text", "label": "9:16", "payload": {"ratio": "9:16"}}},
                    {"action": {"type": "text", "label": "1:1", "payload": {"ratio": "1:1"}}}
                ]
            ]
        }
    
    @staticmethod
    def durations():
        return {
            "inline": True,
            "buttons": [
                [
                    {"action": {"type": "text", "label": "✅ 5 сек", "payload": {"duration": 5}}},
                    {"action": {"type": "text", "label": "10 сек • 30 🍌", "payload": {"duration": 10}}},
                    {"action": {"type": "text", "label": "15 сек • 45 🍌", "payload": {"duration": 15}}}
                ]
            ]
        }
    
    @staticmethod
    def motion_control_types():
        return {
            "inline": True,
            "buttons": [
                [{"action": {"type": "text", "label": "⚡ Standard • Kling 2.6 MC • 720p • 10 🍌", "payload": {"type": "standard", "cost": 10}}}],
                [{"action": {"type": "text", "label": "💎 Pro • Kling 3.0 MC • 720p • 30 🍌", "payload": {"type": "pro", "cost": 30}}}],
                [{"action": {"type": "text", "label": "👤 AI Avatar Pro • от 10 🍌/сек", "payload": {"type": "avatar", "cost": 10}}}],
                [{"action": {"type": "text", "label": "🔊 InfiniTalk from-audio • от 10 🍌/сек", "payload": {"type": "infinitalk", "cost": 10}}}],
                [{"action": {"type": "text", "label": "⬅️ Назад", "payload": {"cmd": "main_menu"}}}]
            ]
        }
    
    @staticmethod
    def photo_creation_step():
        return {
            "inline": True,
            "buttons": [
                [
                    {"action": {"type": "text", "label": "⏭️ Пропустить", "payload": {"action": "skip_refs"}}},
                    {"action": {"type": "text", "label": "✅ Продолжить", "payload": {"action": "continue_refs"}}}
                ],
                [{"action": {"type": "text", "label": "⬅️ Назад", "payload": {"cmd": "main_menu"}}}]
            ]
        }
    
    @staticmethod
    def back_button(cmd: str = "main_menu"):
        return {
            "inline": True,
            "buttons": [
                [{"action": {"type": "text", "label": "⬅️ Назад", "payload": {"cmd": cmd}}}]
            ]
        }

# ==================== ОСНОВНОЙ БОТ ====================

class BananaBoomBot:
    def __init__(self):
        self.bot = Bot(token=Config.VK_TOKEN)
        self.db = Database()
        self.api_client = AIAPIClient()
        self.photo_uploader = PhotoMessageUploader(self.bot.api)
        self.doc_uploader = DocMessageUploader(self.bot.api)
        
        self._setup_handlers()
    
    def _setup_handlers(self):
        bot = self.bot
        
        # === ГЛАВНОЕ МЕНЮ ===
        
        @bot.on.message(CommandRule("start"))
        @bot.on.message(payload={"cmd": "main_menu"})
        async def main_menu_handler(message: Message):
            user = self.db.get_or_create_user(message.from_id)
            
            if user["is_blocked"]:
                await message.answer(
                    f"⛔ Ваш аккаунт заблокирован.\nПричина: {user['block_reason']}"
                )
                return
            
            text = (
                f"🍌 <b>Banana BooM</b> — создавай с AI!\n\n"
                f"✅ <b>Генерация артов:</b> Пиши промпт — получай шедевр\n"
                f"✅ <b>Фото-магия:</b> Стилизация и замена объектов\n"
                f"✅ <b>Видео-продакшн:</b> Делаю ролики из слов и фото\n"
                f"✅ <b>FX-эффекты:</b> Твои видео на миллион\n\n"
                f"🍌 <b>Ваш баланс:</b> {user['balance']} бананов\n\n"
                f"⚠️ Неприемлемый контент запрещён. Аккаунт будет заблокирован без возврата средств.\n\n"
                f"👇 Попробуй прямо сейчас!"
            )
            
            await message.answer(text, keyboard=Keyboards.main_menu())
            self.db.clear_state(message.from_id)
        
        # === СОЗДАНИЕ ВИДЕО ===
        
        @bot.on.message(payload={"cmd": "create_video"})
        async def create_video_handler(message: Message):
            user = self.db.get_or_create_user(message.from_id)
            
            text = (
                f"💰 <b>Стоимость:</b> от 14 бананов\n\n"
                f"Введите промпт для генерации:\n\n"
                f"Опишите видео, которое хотите создать:\n"
                f"• Что происходит в сцене\n"
                f"• Движение камеры\n"
                f"• Стиль и атмосфера\n\n"
                f"Или выберите тип генерации:"
            )
            
            await message.answer(text, keyboard=Keyboards.video_options())
            self.db.set_state(message.from_id, UserState.VIDEO_WAITING_PROMPT.value, {"step": "choose_input"})
        
        @bot.on.message(payload={"input": "text"})
        async def video_text_only_handler(message: Message):
            await message.answer(
                "📝 Введите текстовый промпт для генерации видео:\n\n"
                "Пример: «Девушка в красном платье танцует в неоновом свете, камера движется вокруг, киберпанк стиль»",
                keyboard=Keyboards.back_button("create_video")
            )
            self.db.set_state(message.from_id, UserState.VIDEO_WAITING_PROMPT.value, {"input_type": "text"})
        
        @bot.on.message(payload={"input": "photo_text"})
        async def video_photo_text_handler(message: Message):
            await message.answer(
                "🖼 Отправьте референсное фото, затем напишите промпт.\n"
                "Это поможет сохранить стиль и персонажей.",
                keyboard=Keyboards.back_button("create_video")
            )
            self.db.set_state(message.from_id, UserState.VIDEO_WAITING_PROMPT.value, {"input_type": "photo_text", "photos": []})
        
        # Обработка промпта для видео
        @bot.on.message(lambda msg: self.db.get_state(msg.from_id)[0] == UserState.VIDEO_WAITING_PROMPT.value)
        async def video_prompt_input_handler(message: Message):
            state, data = self.db.get_state(message.from_id)
            
            if message.text and not message.payload:
                prompt = message.text
                data["prompt"] = prompt
                
                # Показываем выбор модели
                await message.answer(
                    f"✅ Промпт получен: «{prompt[:50]}...»\n\n"
                    f"Выберите модель для генерации:",
                    keyboard=Keyboards.video_models()
                )
                self.db.set_state(message.from_id, UserState.VIDEO_WAITING_PROMPT.value, data)
        
        @bot.on.message(payload_contains={"model": str})
        async def video_model_selected_handler(message: Message):
            payload = json.loads(message.payload)
            model = payload.get("model")
            cost = payload.get("cost", 15)
            
            state, data = self.db.get_state(message.from_id)
            prompt = data.get("prompt", "Без промпта")
            
            # Проверяем баланс
            user = self.db.get_or_create_user(message.from_id)
            if user["balance"] < cost:
                await message.answer(
                    f"❌ Недостаточно бананов!\n"
                    f"Требуется: {cost} 🍌\n"
                    f"У вас: {user['balance']} 🍌\n\n"
                    f"Пополните баланс через меню.",
                    keyboard=Keyboards.main_menu()
                )
                return
            
            # Создаём задачу
            task_id = self.db.create_task(
                user_id=message.from_id,
                task_type="video",
                model=model,
                prompt=prompt,
                cost=cost,
                reference_photos=data.get("photos", [])
            )
            
            # Списываем средства
            self.db.update_balance(message.from_id, -cost, f"Генерация видео #{task_id}, модель {model}")
            
            await message.answer(
                f"⏳ <b>Задача #{task_id} создана!</b>\n\n"
                f"🎬 Модель: {model}\n"
                f"💰 Списано: {cost} бананов\n"
                f"🍌 Остаток: {self.db.get_balance(message.from_id)} бананов\n\n"
                f"Генерация началась. Результат придёт в личные сообщения в течение 2-5 минут.",
                keyboard=Keyboards.main_menu()
            )
            
            # Запускаем генерацию в фоне
            asyncio.create_task(self._process_video_task(task_id, model, prompt, data.get("photos")))
            
            self.db.clear_state(message.from_id)
        
        # === MOTION CONTROL ===
        
        @bot.on.message(payload={"cmd": "motion_control"})
        async def motion_control_handler(message: Message):
            text = (
                f"🎬 <b>Motion Control</b>\n\n"
                f"Перенос движения с референсного видео на твоё фото!\n\n"
                f"📝 <b>Как это работает:</b>\n"
                f"1. Загрузи фото персонажа\n"
                f"2. Загрузи видео с движением\n"
                f"3. Получи анимированное фото!\n\n"
                f"🍌 <b>Баланс:</b> {self.db.get_balance(message.from_id)} бананов\n\n"
                f"Выберите тип:"
            )
            await message.answer(text, keyboard=Keyboards.motion_control_types())
        
        @bot.on.message(payload_contains={"type": "standard"})
        @bot.on.message(payload_contains={"type": "pro"})
        async def mc_type_selected_handler(message: Message):
            payload = json.loads(message.payload)
            mc_type = payload.get("type")
            cost = payload.get("cost", 10)
            
            await message.answer(
                f"📸 <b>Шаг 1:</b> Отправьте фото персонажа\n\n"
                f"Тип: {mc_type}\n"
                f"Стоимость: {cost} бананов",
                keyboard=Keyboards.back_button("motion_control")
            )
            
            self.db.set_state(message.from_id, UserState.MC_WAITING_CHARACTER_PHOTO.value, {
                "type": mc_type,
                "cost": cost,
                "character_photo": None,
                "motion_video": None
            })
        
        @bot.on.message(lambda msg: self.db.get_state(msg.from_id)[0] == UserState.MC_WAITING_CHARACTER_PHOTO.value)
        async def mc_character_photo_handler(message: Message):
            if not message.attachments or not any(att.photo for att in message.attachments):
                await message.answer("❌ Пожалуйста, отправьте фото персонажа.")
                return
            
            # Сохраняем фото
            photo = message.attachments[0].photo
            photo_url = photo.sizes[-1].url if photo.sizes else None
            
            state, data = self.db.get_state(message.from_id)
            data["character_photo"] = photo_url
            
            await message.answer(
                "✅ Фото персонажа получено!\n\n"
                "🎥 <b>Шаг 2:</b> Теперь отправьте видео с движением для переноса.",
                keyboard=Keyboards.back_button("motion_control")
            )
            self.db.set_state(message.from_id, UserState.MC_WAITING_MOTION_VIDEO.value, data)
        
        @bot.on.message(lambda msg: self.db.get_state(msg.from_id)[0] == UserState.MC_WAITING_MOTION_VIDEO.value)
        async def mc_motion_video_handler(message: Message):
            # Проверяем видео во вложениях
            has_video = any(att.video for att in (message.attachments or []))
            if not has_video:
                await message.answer("❌ Пожалуйста, отправьте видео с движением.")
                return
            
            state, data = self.db.get_state(message.from_id)
            cost = data.get("cost", 10)
            
            # Проверяем баланс
            if self.db.get_balance(message.from_id) < cost:
                await message.answer("❌ Недостаточно бананов!", keyboard=Keyboards.main_menu())
                return
            
            # Создаём задачу
            task_id = self.db.create_task(
                user_id=message.from_id,
                task_type="motion_control",
                model=data.get("type"),
                prompt="Motion control generation",
                cost=cost,
                reference_photos=[data.get("character_photo")]
            )
            
            self.db.update_balance(message.from_id, -cost, f"Motion Control #{task_id}")
            
            await message.answer(
                f"⏳ <b>Задача #{task_id} создана!</b>\n"
                f"Motion Control обрабатывается. Ожидайте результат.",
                keyboard=Keyboards.main_menu()
            )
            
            asyncio.create_task(self._process_motion_task(task_id, data))
            self.db.clear_state(message.from_id)
        
        # === СОЗДАНИЕ ФОТО ===
        
        @bot.on.message(payload={"cmd": "create_photo"})
        async def create_photo_handler(message: Message):
            user = self.db.get_or_create_user(message.from_id)
            
            text = (
                f"🖼 <b>Создание фото</b>\n\n"
                f"🍌 <b>Ваш баланс:</b> {user['balance']} бананов\n\n"
                f"<b>Шаг 1:</b> Загрузка референсов (опционально)\n\n"
                f"Загрузите изображения для:\n"
                f"• Точного сходства с объектом\n"
                f"• Сохранения стиля\n"
                f"• Персонажей (до 14 фото)\n\n"
                f"После загрузки нажмите «Продолжить» или «Пропустить»\n\n"
                f"Загружено: 0/14\n\n"
                f"Это бесплатно!"
            )
            
            await message.answer(text, keyboard=Keyboards.photo_creation_step())
            self.db.set_state(message.from_id, UserState.PHOTO_WAITING_REFERENCES.value, {"photos": []})
        
        @bot.on.message(lambda msg: self.db.get_state(msg.from_id)[0] == UserState.PHOTO_WAITING_REFERENCES.value)
        async def photo_references_handler(message: Message):
            state, data = self.db.get_state(message.from_id)
            
            # Обработка кнопок
            if message.payload:
                payload = json.loads(message.payload)
                action = payload.get("action")
                
                if action == "skip_refs":
                    await message.answer(
                        "⏭️ Референсы пропущены.\n\n"
                        "📝 Введите промпт для генерации фото:",
                        keyboard=Keyboards.back_button("create_photo")
                    )
                    self.db.set_state(message.from_id, UserState.PHOTO_WAITING_PROMPT.value, data)
                    return
                
                elif action == "continue_refs":
                    if not data.get("photos"):
                        await message.answer("❌ Вы не загрузили ни одного фото!")
                        return
                    
                    await message.answer(
                        f"✅ Загружено {len(data['photos'])} фото.\n\n"
                        "📝 Введите промпт для генерации:",
                        keyboard=Keyboards.back_button("create_photo")
                    )
                    self.db.set_state(message.from_id, UserState.PHOTO_WAITING_PROMPT.value, data)
                    return
            
            # Обработка фото
            if message.attachments:
                photos = [att for att in message.attachments if att.photo]
                if photos:
                    for photo in photos:
                        photo_url = photo.photo.sizes[-1].url if photo.photo.sizes else None
                        if photo_url and len(data["photos"]) < 14:
                            data["photos"].append(photo_url)
                    
                    await message.answer(
                        f"📸 Загружено: {len(data['photos'])}/14\n"
                        f"Отправьте ещё фото или нажмите «Продолжить»/«Пропустить»",
                        keyboard=Keyboards.photo_creation_step()
                    )
                    self.db.set_state(message.from_id, state, data)
        
        @bot.on.message(lambda msg: self.db.get_state(msg.from_id)[0] == UserState.PHOTO_WAITING_PROMPT.value)
        async def photo_prompt_handler(message: Message):
            if not message.text or message.payload:
                return
            
            state, data = self.db.get_state(message.from_id)
            prompt = message.text
            cost = Config.PRICES["photo_generate"]
            
            if self.db.get_balance(message.from_id) < cost:
                await message.answer("❌ Недостаточно бананов!", keyboard=Keyboards.main_menu())
                return
            
            task_id = self.db.create_task(
                user_id=message.from_id,
                task_type="photo",
                model="flux_ultra",
                prompt=prompt,
                cost=cost,
                reference_photos=data.get("photos", [])
            )
            
            self.db.update_balance(message.from_id, -cost, f"Генерация фото #{task_id}")
            
            await message.answer(
                f"⏳ <b>Генерация фото #{task_id} началась!</b>\n"
                f"Ожидайте результат...",
                keyboard=Keyboards.main_menu()
            )
            
            asyncio.create_task(self._process_photo_task(task_id, prompt, data.get("photos")))
            self.db.clear_state(message.from_id)
        
        # === АНАЛИЗ ФОТО (Фото→Промпт) ===
        
        @bot.on.message(payload={"cmd": "photo_analysis"})
        async def photo_analysis_handler(message: Message):
            text = (
                f"📸 <b>Анализ фото → Промпт</b>\n\n"
                f"🍌 <b>Баланс:</b> {self.db.get_balance(message.from_id)} 🍌\n"
                f"📷 <b>Отправлено фото:</b> 0\n\n"
                f"Отправьте фото для анализа.\n"
                f"🤖 ИИ создаст точный промпт для повторения:\n"
                f"• Лица и люди\n"
                f"• Позы и одежда\n"
                f"• Освещение и фон\n\n"
                f"<b>Это бесплатно!</b>"
            )
            
            await message.answer(text, keyboard=Keyboards.back_button("main_menu"))
            self.db.set_state(message.from_id, UserState.ANALYSIS_WAITING_PHOTO.value, {})
        
        @bot.on.message(lambda msg: self.db.get_state(msg.from_id)[0] == UserState.ANALYSIS_WAITING_PHOTO.value)
        async def photo_analysis_upload_handler(message: Message):
            if not message.attachments or not any(att.photo for att in message.attachments):
                await message.answer("❌ Пожалуйста, отправьте фото для анализа.")
                return
            
            photo = message.attachments[0].photo
            photo_url = photo.sizes[-1].url if photo.sizes else None
            
            await message.answer("🔍 Анализирую фото...")
            
            # Анализ через API
            async with self.api_client:
                prompt = await self.api_client.analyze_photo(photo_url)
            
            await message.answer(
                f"✅ <b>Анализ завершён!</b>\n\n"
                f"📝 <b>Сгенерированный промпт:</b>\n"
                f"<code>{prompt}</code>\n\n"
                f"Скопируйте его и используйте для генерации!",
                keyboard=Keyboards.main_menu()
            )
            
            self.db.clear_state(message.from_id)
        
        # === ПОПОЛНЕНИЕ БАЛАНСА ===
        
        @bot.on.message(payload={"cmd": "top_up"})
        async def top_up_handler(message: Message):
            text = (
                f"💰 <b>Пополнение баланса</b>\n\n"
                f"Текущий баланс: {self.db.get_balance(message.from_id)} 🍌\n\n"
                f"Выберите пакет:\n"
                f"• 50 бананов — 150₽\n"
                f"• 120 бананов — 300₽\n"
                f"• 300 бананов — 600₽\n"
                f"• 1000 бананов — 1500₽\n\n"
                f"Для пополнения напишите в поддержку: @support"
            )
            await message.answer(text, keyboard=Keyboards.main_menu())
        
        # === ТЕХПОДДЕРЖКА ===
        
        @bot.on.message(payload={"cmd": "support"})
        async def support_handler(message: Message):
            await message.answer(
                f"🔧 <b>Техническая поддержка</b>\n\n"
                f"По вопросам пополнения, багов и сотрудничества:\n"
                f"@support_manager\n\n"
                f"Канал с обновлениями: @banana_boom_channel",
                keyboard=Keyboards.main_menu()
            )
        
        # === ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД ===
        
        @bot.on.message()
        async def unknown_handler(message: Message):
            await message.answer(
                "Не понял команду. Используйте меню:",
                keyboard=Keyboards.main_menu()
            )
    
    # ==================== ФОНОВЫЕ ЗАДАЧИ ====================
    
    async def _process_video_task(self, task_id: int, model: str, prompt: str, photos: list = None):
        """Обработка задачи генерации видео"""
        try:
            self.db.update_task_status(task_id, "processing")
            
            async with self.api_client:
                if "kling" in model:
                    result_url = await self.api_client.generate_video_kling(prompt, photos[0] if photos else None, model)
                elif "haiper" in model:
                    result_url = await self.api_client.generate_video_haiper(prompt, photos[0] if photos else None)
                elif "seedance" in model:
                    version = "1.5" if "15" in model else "2.0"
                    result_url = await self.api_client.generate_video_seedance(prompt, photos[0] if photos else None, version)
                elif "veo" in model:
                    result_url = await self.api_client.generate_video_veo(prompt, photos[0] if photos else None)
                elif "grok" in model:
                    result_url = await self.api_client.generate_video_grok(photos[0] if photos else prompt)
                else:
                    result_url = await self.api_client.generate_video_kling(prompt, photos[0] if photos else None)
            
            self.db.update_task_status(task_id, "completed", result_url)
            
            # Отправляем результат пользователю
            # TODO: Скачать видео и отправить через VK API
            # Пока отправляем ссылку
            
        except Exception as e:
            logging.error(f"Task {task_id} failed: {e}")
            self.db.update_task_status(task_id, "failed", error_message=str(e))
    
    async def _process_photo_task(self, task_id: int, prompt: str, photos: list = None):
        """Обработка задачи генерации фото"""
        try:
            self.db.update_task_status(task_id, "processing")
            
            async with self.api_client:
                result_url = await self.api_client.generate_photo(prompt, photos)
            
            self.db.update_task_status(task_id, "completed", result_url)
            
        except Exception as e:
            logging.error(f"Photo task {task_id} failed: {e}")
            self.db.update_task_status(task_id, "failed", error_message=str(e))
    
    async def _process_motion_task(self, task_id: int, data: dict):
        """Обработка Motion Control"""
        try:
            self.db.update_task_status(task_id, "processing")
            # TODO: Реальная интеграция с API Motion Control
            await asyncio.sleep(5)
            self.db.update_task_status(task_id, "completed", "https://example.com/mc_result.mp4")
        except Exception as e:
            self.db.update_task_status(task_id, "failed", error_message=str(e))
    
    # ==================== ЗАПУСК ====================
    
    async def run(self):
        logging.basicConfig(level=logging.INFO)
        print("🍌 Banana Boom Bot запущен!")
        await self.bot.run_polling()

# ==================== ТОЧКА ВХОДА ====================

if __name__ == "__main__":
    bot = BananaBoomBot()
    asyncio.run(bot.run())
Что реализовано в коде:
Архитектура:
База данных SQLite — пользователи, транзакции, задачи, состояния FSM
FSM (Finite State Machine) — отслеживание состояний пользователя (ожидание фото, промпта и т.д.)
Модульная структура — легко добавлять новые модели и функции
Функционал:
✅ Главное меню с балансом
✅ Создание видео (выбор моделей: Kling, Seedance, Haiper, Veo, Grok)
✅ Motion Control (Standard/Pro/AI Avatar/InfiniTalk)
✅ Создание фото с референсами (до 14 фото)
✅ Анализ фото → промпт (бесплатно)
✅ Система "бананов" — внутренняя валюта
✅ Проверка баланса перед генерацией
Что нужно доделать для продакшена:
Реальные API интеграции — заменить заглушки в AIAPIClient на реальные запросы к Kling API, Haiper API и т.д. (требуются API-ключи и бизнес-договоры)
Загрузка файлов — реализовать скачивание видео/фото из VK и загрузку результатов обратно
Платёжная система — интеграция с ЮKassa, CryptoBot или другими для пополнения баланса
Админ-панель — команды для просмотра статистики, блокировки пользователей, ручного пополнения баланса