import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import tempfile
import time
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from vkbottle.bot import Bot, Message
from vkbottle.callback import BotCallback
from vkbottle.dispatch.rules.base import ABCRule, CommandRule, PayloadRule
from vkbottle.tools import DocMessagesUploader, PhotoMessageUploader

from tbank_payment.client import TBankPaymentClient as TBankAPI
from tbank_payment.models import InitPaymentRequest
from tbank_payment.utils import generate_token


class TextExistsRule(ABCRule):

    async def check(self, event: Message) -> bool:
        return bool(event.text)


class NoPayloadRule(ABCRule):
    async def check(self, event: Message) -> bool:
        return not bool(event.payload)


class PayloadContainsRule(ABCRule):
    def __init__(self, key: str):
        self.key = key

    async def check(self, event: Message) -> bool:
        if not event.payload:
            return False
        try:
            return self.key in json.loads(event.payload)
        except:
            return False


class DBStateRule(ABCRule):
    def __init__(self, db, state):
        self.db = db
        self.state = state

    async def check(self, event: Message) -> bool:
        try:
            current_state, _ = self.db.get_state(event.from_id)
            return current_state == self.state
        except:
            return False


load_dotenv()

# ==================== КОНФИГУРАЦИЯ ====================


class Config:
    VK_TOKEN = os.getenv("VK_GROUP_TOKEN")
    VK_GROUP_ID = int(os.getenv("VK_GROUP_ID"))
    ADMIN_ID = int(
        os.getenv("ADMIN_IDS", "381643597").split(",")[0]
        if os.getenv("ADMIN_IDS")
        else 381643597
    )

    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://vkkling.chillcreative.ru")
    WEBHOOK_URL_VK = f"{WEBHOOK_HOST}/vk"
    WEBHOOK_URL = f"{WEBHOOK_HOST}/webhook"

    # API ключи из .env
    KLING_API_KEY = os.getenv("KIE_AI_API_KEY", "")
    HAIPE_API_KEY = os.getenv("HAIPE_API_KEY", "")
    SEEDANCE_API_KEY = os.getenv("SEEDANCE_API_KEY", "")
    VEO_API_KEY = os.getenv("VEO_API_KEY", "")
    GROK_API_KEY = os.getenv("GROK_API_KEY", "")
    PIAPI_KEY = os.getenv("PIAPI_KEY", "")
    NOVITA_API_KEY = os.getenv("NOVITA_API_KEY", "")
    REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

    # T-Bank
    TBANK_TERMINAL_KEY = os.getenv("TBANK_TERMINAL_KEY", "")
    TBANK_SECRET_KEY = os.getenv("TBANK_SECRET_KEY", "")
    TBANK_IS_TEST = os.getenv("TBANK_IS_TEST", "false").lower() == "true"
    TBANK_API_URL = os.getenv("TBANK_API_URL", "https://securepay.tinkoff.ru/v2/")

    # Базовые цены в 🍌
    PRICES = {
        "photo_generate": 5,
        "nano_banana": 8,
        "nano_banana_2": 8,
        "nano_banana_pro": 8,
        "seedream_text": 6,
        "seedream_edit": 8,
        "video_kling_3_std": 15,
        "video_kling_3_pro": 15,
        "video_seedance_15": 14,
        "video_seedance_20": 17,
        "video_kling3": 15,
        "video_seedance2": 17,
        "video_grok_img2video": 20,
        "video_haiper_23": 18,
        "video_veo_31": 30,
        "video_grok_text2video": 18,
        "motion_control_standard": 10,
        "motion_control_pro": 30,
        "ai_avatar_pro": 10,
        "infinitalk": 10,
        "photo_analysis": 0,
    }

    PACKAGES = {250: 30, 400: 40, 700: 100, 1400: 200}

    # Начальный баланс новых пользователей
    STARTING_BALANCE = 10

    # Пути
    DB_PATH = "vkbanana.db"
    UPLOAD_DIR = "uploads"
    OUTPUT_DIR = "outputs"


# Создаём директории
Path(Config.UPLOAD_DIR).mkdir(exist_ok=True)
Path(Config.OUTPUT_DIR).mkdir(exist_ok=True)
Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    filename="logs/vk_bot.log",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# Set tbank logger to DEBUG
logging.getLogger("tbank_payment").setLevel(logging.DEBUG)


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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS generation_tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_type TEXT,
                model TEXT,
                prompt TEXT,
                reference_photos TEXT,
                status TEXT DEFAULT 'pending',
                cost INTEGER,
                result_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                api_task_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                order_id TEXT UNIQUE,
                tbank_payment_id TEXT,
                amount_rub INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        conn.commit()
        conn.close()

    def get_or_create_user(self, user_id: int) -> dict:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            cursor.execute(
                "INSERT INTO users (user_id, balance) VALUES (?, ?)",
                (user_id, Config.STARTING_BALANCE),
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
            "block_reason": user[5],
        }

    def update_balance(self, user_id: int, amount: int, reason: str) -> bool:
        conn = self.get_connection()
        cursor = conn.cursor()
        if amount < 0:
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            current = cursor.fetchone()
            if not current or current[0] + amount < 0:
                conn.close()
                return False
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id),
        )
        cursor.execute(
            "INSERT INTO transactions (user_id, amount, reason) VALUES (?, ?, ?)",
            (user_id, amount, reason),
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

    def set_state(self, user_id: int, state: str, data: dict = None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO user_states (user_id, state, data, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (user_id, state, json.dumps(data or {})),
        )
        conn.commit()
        conn.close()

    def get_state(self, user_id: int) -> tuple:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT state, data FROM user_states WHERE user_id = ?", (user_id,)
        )
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

    def create_task(
        self,
        user_id: int,
        task_type: str,
        model: str,
        prompt: str,
        cost: int,
        reference_photos: list = None,
    ) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO generation_tasks (user_id, task_type, model, prompt, reference_photos, cost) VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id,
                task_type,
                model,
                prompt,
                json.dumps(reference_photos or []),
                cost,
            ),
        )
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return task_id

    def update_task_status(
        self,
        task_id: int,
        status: str,
        result_url: str = None,
        error_message: str = None,
        api_task_id: str = None,
    ):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE generation_tasks SET status = ?, result_url = COALESCE(?, result_url), error_message = COALESCE(?, error_message), api_task_id = COALESCE(?, api_task_id), completed_at = CASE WHEN ? IN ('completed', 'failed') THEN CURRENT_TIMESTAMP ELSE NULL END WHERE task_id = ?",
            (status, result_url, error_message, api_task_id, status, task_id),
        )
        conn.commit()
        conn.close()

    def get_task_user(self, task_id: int) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM generation_tasks WHERE task_id = ?", (task_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def get_task_details(self, task_id: int) -> Optional[dict]:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, cost, status, error_message, result_url
            FROM generation_tasks WHERE task_id = ?
        """,
            (task_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "user_id": row[0],
                "cost": row[1],
                "status": row[2],
                "error_message": row[3],
                "result_url": row[4],
            }
        return None

    def create_pending_payment(
        self, user_id: int, order_id: str, amount_rub: int
    ) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO payments (user_id, order_id, amount_rub, status) VALUES (?, ?, ?, 'pending')",
            (user_id, order_id, amount_rub),
        )
        payment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return payment_id

    def get_payment_by_tbank_id(self, tbank_payment_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM payments WHERE tbank_payment_id = ?", (tbank_payment_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "user_id": row[1],
                "order_id": row[2],
                "tbank_payment_id": row[3],
                "amount_rub": row[4],
                "status": row[5],
            }
        return None

    def update_payment_tbank_id(self, payment_id: int, tbank_payment_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE payments SET tbank_payment_id = ? WHERE id = ?",
            (tbank_payment_id, payment_id),
        )
        conn.commit()
        conn.close()

    def update_payment_status(self, payment_id: int, status: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE payments SET status = ? WHERE id = ?", (status, payment_id)
        )
        conn.commit()
        conn.close()

    def get_payment_by_order_id(self, order_id: str):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM payments WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                "id": row[0],
                "user_id": row[1],
                "order_id": row[2],
                "tbank_payment_id": row[3],
                "amount_rub": row[4],
                "status": row[5],
            }
        return None


# ==================== СОСТОЯНИЯ БОТА ====================


class UserState(Enum):
    IDLE = "idle"
    VIDEO_WAITING_PROMPT = "video_waiting_prompt"
    PHOTO_WAITING_PROMPT = "photo_waiting_prompt"
    PHOTO_WAITING_REFERENCES = "photo_waiting_references"
    MC_WAITING_CHARACTER_PHOTO = "mc_waiting_character_photo"
    MC_WAITING_PROMPT = "mc_waiting_prompt"
    MC_WAITING_MOTION_VIDEO = "mc_waiting_motion_video"
    ANALYSIS_WAITING_PHOTO = "analysis_waiting_photo"
    REF_VIDEO_WAITING_REFS = "ref_video_waiting_refs"
    REF_VIDEO_MODEL = "ref_video_model"
    REF_VIDEO_ASPECT = "ref_video_aspect"
    REF_VIDEO_DURATION = "ref_video_duration"
    REF_VIDEO_CONFIG = "ref_video_config"
    PHOTO_WAITING_MODEL = "photo_waiting_model"
    PHOTO_WAITING_ASPECT = "photo_waiting_aspect"
    VIDEO_WAITING_MODEL = "video_waiting_model"
    VIDEO_WAITING_ASPECT = "video_waiting_aspect"


# ==================== API КЛИЕНТЫ ====================


class AIAPIClient:
    def __init__(self):
        self.session = None

    async def upload_file_to_kie(
        self, file_path: str, api_key: str, upload_path: str = "motioncontrol"
    ) -> str:
        """Upload local file to KIE /api/file-upload via multipart, return KIE URL"""
        headers = {"Authorization": f"Bearer {api_key}"}
        form = aiohttp.FormData()
        form.add_field(
            "file", open(file_path, "rb"), filename=os.path.basename(file_path)
        )
        form.add_field("uploadPath", upload_path)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.kie.ai/api/file-upload", headers=headers, data=form
            ) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]["downloadUrl"]
                raise ValueError(result.get("msg", "File upload failed"))

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def analyze_photo(self, photo_url: str) -> str:
        headers = {
            "Authorization": f"Bearer {Config.KLING_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Составь подробное описание изображения для генерации похожего в Nano Banana Pro. Сохрани все мелкие детали, лицо, одежду, позу, освещение, стиль, цвета. На русском языке.",
                        },
                        {"type": "image_url", "image_url": {"url": photo_url}},
                    ],
                }
            ],
            "stream": False,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.kie.ai/gemini-3.1-pro/v1/chat/completions",
                headers=headers,
                json=data,
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise ValueError(f"Gemini error {resp.status}: {text}")
                try:
                    result = json.loads(text)
                except json.JSONDecodeError as e:
                    logging.error(
                        f"JSON decode error in analyze_photo: {text[:500]}... Error: {e}"
                    )
                    raise ValueError(f"Invalid JSON response from Gemini: {text[:200]}")
                if "choices" not in result or not result["choices"]:
                    raise ValueError(f"Unexpected Gemini response structure: {result}")
                return result["choices"][0]["message"]["content"]

    async def create_grok_task(self, grok_model: str, input_data: dict) -> str:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {Config.GROK_API_KEY}",
                "Content-Type": "application/json",
            }
            data = {
                "model": grok_model,
                "callBackUrl": Config.WEBHOOK_URL,
                "input": input_data,
            }
            async with session.post(
                "https://api.kie.ai/api/v1/jobs/createTask", headers=headers, json=data
            ) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]["taskId"]
                raise ValueError(result.get("msg", "Grok create task failed"))

    async def get_grok_task_detail(self, task_id: str) -> dict:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {Config.GROK_API_KEY}"}
            url = f"https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId={task_id}"
            async with session.get(url, headers=headers) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]
                raise ValueError(result.get("msg", "Grok get task failed"))

    async def create_seadream_task(self, model_name: str, input_data: dict) -> str:
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {Config.KLING_API_KEY}",
                "Content-Type": "application/json",
            }
            data = {
                "model": model_name,
                "callBackUrl": Config.WEBHOOK_URL,
                "input": input_data,
            }
            async with session.post(
                "https://api.kie.ai/api/v1/jobs/createTask", headers=headers, json=data
            ) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]["taskId"]
                raise ValueError(
                    result.get("msg", f"SeaDream {model_name} create task failed")
                )

    async def get_seadream_task_detail(self, task_id: str) -> dict:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {Config.KLING_API_KEY}"}
            url = f"https://api.kie.ai/api/v1/jobs/getTaskDetail?taskId={task_id}"
            async with session.get(url, headers=headers) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]
                raise ValueError(result.get("msg", "SeaDream get task failed"))

    async def create_kie_task(self, model: str, input_data: dict, api_key: str) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": model,
            "callBackUrl": Config.WEBHOOK_URL,
            "input": input_data,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.kie.ai/api/v1/jobs/createTask", headers=headers, json=data
            ) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]["taskId"]
                raise ValueError(result.get("msg", "KIE task creation failed"))

    async def upload_url_to_kie(
        self, file_url: str, api_key: str, upload_path: str = "motioncontrol"
    ) -> str:
        """Upload file by URL to KIE /api/file-url-upload, return KIE URL"""
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "fileUrl": file_url,
            "uploadPath": upload_path,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.kie.ai/api/file-url-upload", headers=headers, json=data
            ) as resp:
                result = await resp.json()
                if result.get("code") == 200:
                    return result["data"]["downloadUrl"]
                raise ValueError(result.get("msg", "URL upload failed"))

    async def get_direct_mp4_url(self, vk_doc_url: str) -> str:
        """Follow redirects on VK doc URL to get direct MP4 URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                vk_doc_url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200 and "mp4" in str(resp.url).lower():
                    return str(resp.url)
                raise ValueError(
                    f"Not direct MP4, status: {resp.status}, url: {resp.url}"
                )


# ==================== КЛАВИАТУРЫ ====================


class Keyboards:
    @staticmethod
    def add_highlights(buttons, data):
        """Подсвечивает выбранные кнопки синим цветом на основе состояния data."""
        if not data:
            return buttons
        for row in buttons:
            for btn in row:
                action = btn.get("action", {})
                payload_str = action.get("payload")
                if isinstance(payload_str, str):
                    try:
                        payload = json.loads(payload_str)
                        highlighted = False
                        for key, value in payload.items():
                            if (
                                key not in ("cmd", "action", "input", "type")
                                and data.get(key) == value
                            ):
                                highlighted = True
                                break
                        if highlighted:
                            btn["color"] = "primary"
                    except json.JSONDecodeError:
                        pass
        return buttons

    @staticmethod
    def main_menu(data=None):
        buttons = [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🎬 Создать видео",
                        "payload": {"cmd": "create_video"},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🖼 Создать фото",
                        "payload": {"cmd": "create_photo"},
                    }
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🎥 Motion Control",
                        "payload": {"cmd": "motion_control"},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "📸 Фото= промпт",
                        "payload": {"cmd": "photo_analysis"},
                    }
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "💰 Пополнить",
                        "payload": {"cmd": "top_up"},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🔧 Тех поддержка",
                        "payload": {"cmd": "support"},
                    }
                },
            ],
        ]
        buttons = Keyboards.add_highlights(buttons, data or {})
        return json.dumps(
            {
                "inline": True,
                "buttons": buttons,
            }
        )

    @staticmethod
    def video_options():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "📝 Текст",
                                "payload": {"input": "text"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "🎥 Видео по референсам",
                                "payload": {"cmd": "ref_video"},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "main_menu"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def video_models(data=None):
        buttons = [
            # Kling std
            [
                {
                    "action": {
                        "type": "text",
                        "label": "⚡std 16:9 15🍌",
                        "payload": {
                            "model": "kling_3_std",
                            "aspect": "16:9",
                            "cost": 15,
                        },
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "std 9:16 15🍌",
                        "payload": {
                            "model": "kling_3_std",
                            "aspect": "9:16",
                            "cost": 15,
                        },
                    }
                },
            ],
            # Kling pro
            [
                {
                    "action": {
                        "type": "text",
                        "label": "💎pro 16:9 15🍌",
                        "payload": {
                            "model": "kling_3_pro",
                            "aspect": "16:9",
                            "cost": 15,
                        },
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "pro 9:16 15🍌",
                        "payload": {
                            "model": "kling_3_pro",
                            "aspect": "9:16",
                            "cost": 15,
                        },
                    }
                },
            ],
            # Kling squares
            [
                {
                    "action": {
                        "type": "text",
                        "label": "std 1:1 15🍌",
                        "payload": {
                            "model": "kling_3_std",
                            "aspect": "1:1",
                            "cost": 15,
                        },
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "pro 1:1 15🍌",
                        "payload": {
                            "model": "kling_3_pro",
                            "aspect": "1:1",
                            "cost": 15,
                        },
                    }
                },
            ],
            # Seedance 1.5
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🌱s1.5 16:9 14🍌",
                        "payload": {
                            "model": "seedance_15",
                            "aspect": "16:9",
                            "cost": 14,
                        },
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "s1.5 9:16 14🍌",
                        "payload": {
                            "model": "seedance_15",
                            "aspect": "9:16",
                            "cost": 14,
                        },
                    }
                },
            ],
            # Seedance squares + back
            [
                {
                    "action": {
                        "type": "text",
                        "label": "s1.5 1:1 14🍌",
                        "payload": {
                            "model": "seedance_15",
                            "aspect": "1:1",
                            "cost": 14,
                        },
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Назад",
                        "payload": {"cmd": "create_video"},
                    }
                },
            ],
        ]
        buttons = Keyboards.add_highlights(buttons, data or {})
        return json.dumps(
            {
                "inline": True,
                "buttons": buttons,
            }
        )

    @staticmethod
    def photo_models(data=None):
        buttons = [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🖼 Flux • 5 🍌",
                        "payload": {"photo_model": "flux", "cost": 5},
                    }
                }
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🍌 Nano Banana 2 • 8 🍌",
                        "payload": {"photo_model": "nano_banana_2", "cost": 8},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🍌 Nano Banana Pro • 8 🍌",
                        "payload": {
                            "photo_model": "nano_banana_pro",
                            "cost": 8,
                        },
                    }
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🌱 Seedream Text • 6 🍌",
                        "payload": {"photo_model": "seedream_text", "cost": 6},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🌱 Seedream Edit • 8 🍌",
                        "payload": {"photo_model": "seedream_edit", "cost": 8},
                    }
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Назад",
                        "payload": {"cmd": "create_photo"},
                    }
                }
            ],
        ]
        buttons = Keyboards.add_highlights(buttons, data or {})
        return json.dumps(
            {
                "inline": True,
                "buttons": buttons,
            }
        )

    @staticmethod
    def photo_models_kb(has_refs: bool):
        cost = 8 if has_refs else 6
        model = "seedream_edit" if has_refs else "seedream_text"
        mode = "Edit" if has_refs else "T2I"
        buttons = [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🍌 Nano Banana 2 (8🍌)",
                        "payload": {"photo_model": "nano_banana_2", "cost": 8},
                    }
                }
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🍌 Nano Banana Pro (8🍌)",
                        "payload": {"photo_model": "nano_banana_pro", "cost": 8},
                    }
                }
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": f"🌱 Seedream {mode} ({cost}🍌)",
                        "payload": {"photo_model": model, "cost": cost},
                    }
                }
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Назад",
                        "payload": {"cmd": "create_photo"},
                    }
                }
            ],
        ]
        return json.dumps({"inline": True, "buttons": buttons})

    @staticmethod
    def photo_aspects_kb():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "16:9",
                                "payload": {"aspect": "16:9"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "9:16",
                                "payload": {"aspect": "9:16"},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "1:1",
                                "payload": {"aspect": "1:1"},
                            }
                        }
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "create_photo"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def photo_aspects_keyboard():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "16:9",
                                "payload": {"aspect": "16:9"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "9:16",
                                "payload": {"aspect": "9:16"},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "1:1",
                                "payload": {"aspect": "1:1"},
                            }
                        }
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "create_photo"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def video_models():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⚡std 16:9",
                                "payload": {
                                    "model": "kling_3_std",
                                    "aspect": "16:9",
                                    "cost": 15,
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "std 9:16",
                                "payload": {
                                    "model": "kling_3_std",
                                    "aspect": "9:16",
                                    "cost": 15,
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "std 1:1",
                                "payload": {
                                    "model": "kling_3_std",
                                    "aspect": "1:1",
                                    "cost": 15,
                                },
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "💎pro 16:9",
                                "payload": {
                                    "model": "kling_3_pro",
                                    "aspect": "16:9",
                                    "cost": 15,
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "pro 9:16",
                                "payload": {
                                    "model": "kling_3_pro",
                                    "aspect": "9:16",
                                    "cost": 15,
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "pro 1:1",
                                "payload": {
                                    "model": "kling_3_pro",
                                    "aspect": "1:1",
                                    "cost": 15,
                                },
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "🌱s1.5 16:9",
                                "payload": {
                                    "model": "seedance_15",
                                    "aspect": "16:9",
                                    "cost": 14,
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "s1.5 9:16",
                                "payload": {
                                    "model": "seedance_15",
                                    "aspect": "9:16",
                                    "cost": 14,
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "s1.5 1:1",
                                "payload": {
                                    "model": "seedance_15",
                                    "aspect": "1:1",
                                    "cost": 14,
                                },
                            }
                        },
                    ],
                ],
            }
        )

    @staticmethod
    def photo_creation_step():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⏭️ Пропустить",
                                "payload": {"action": "skip_refs"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "✅ Продолжить",
                                "payload": {"action": "continue_refs"},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "main_menu"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def ref_creation_step():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⏭️ Без рефов",
                                "payload": {"action": "skip_refs"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "✅ Готово",
                                "payload": {"action": "refs_ready"},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "main_menu"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def regular_back(cmd: str = "main_menu"):
        return json.dumps(
            {
                "one_time": False,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": cmd},
                            }
                        }
                    ]
                ],
            }
        )

    @staticmethod
    def motion_control_types():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "Standard (10🍌)",
                                "payload": {"type": "standard", "cost": 10},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "Pro (30🍌)",
                                "payload": {"type": "pro", "cost": 30},
                            }
                        },
                    ]
                ],
            }
        )

    @staticmethod
    def ref_combined_kb(data: dict = None):
        data = data or {}
        ref_model = data.get("ref_model")
        kling_mode = data.get("kling_mode")
        duration = data.get("duration")
        aspect = data.get("aspect")

        def get_color(selected):
            return "primary" if selected else "secondary"

        buttons = []
        # Models
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🤖 Grok",
                        "payload": {"cmd": "ref_model", "ref_model": "grok"},
                    },
                    "color": get_color(ref_model == "grok"),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "⚡ Kling std",
                        "payload": {
                            "cmd": "ref_model",
                            "ref_model": "kling3",
                            "kling_mode": "std",
                        },
                    },
                    "color": get_color(ref_model == "kling3" and kling_mode == "std"),
                },
            ]
        )
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "⚡ Kling pro",
                        "payload": {
                            "cmd": "ref_model",
                            "ref_model": "kling3",
                            "kling_mode": "pro",
                        },
                    },
                    "color": get_color(ref_model == "kling3" and kling_mode == "pro"),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🌿 Seedance2",
                        "payload": {"cmd": "ref_model", "ref_model": "seedance2"},
                    },
                    "color": get_color(ref_model == "seedance2"),
                },
            ]
        )
        # Durations
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "6s",
                        "payload": {"cmd": "ref_duration", "ref_duration": 6},
                    },
                    "color": get_color(duration == 6),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "10s",
                        "payload": {"cmd": "ref_duration", "ref_duration": 10},
                    },
                    "color": get_color(duration == 10),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "15s",
                        "payload": {"cmd": "ref_duration", "ref_duration": 15},
                    },
                    "color": get_color(duration == 15),
                },
            ]
        )
        # Aspects
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "16:9",
                        "payload": {"cmd": "ref_aspect", "ref_aspect": "16:9"},
                    },
                    "color": get_color(aspect == "16:9"),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "9:16",
                        "payload": {"cmd": "ref_aspect", "ref_aspect": "9:16"},
                    },
                    "color": get_color(aspect == "9:16"),
                },
            ]
        )
        # Back
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Назад",
                        "payload": {"cmd": "ref_video"},
                    }
                }
            ]
        )
        return json.dumps({"inline": True, "buttons": buttons})

    @staticmethod
    def ref_models_kb():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "🤖 Grok (20🍌)",
                                "payload": {"cmd": "ref_model", "ref_model": "grok"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "⚡ Kling std",
                                "payload": {
                                    "cmd": "ref_model",
                                    "ref_model": "kling3",
                                    "kling_mode": "std",
                                },
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⚡ Kling pro",
                                "payload": {
                                    "cmd": "ref_model",
                                    "ref_model": "kling3",
                                    "kling_mode": "pro",
                                },
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "🌿 Seedance2",
                                "payload": {
                                    "cmd": "ref_model",
                                    "ref_model": "seedance2",
                                },
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "ref_video"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def ref_durations_kb():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "6s",
                                "payload": {"cmd": "ref_duration", "ref_duration": 6},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "10s",
                                "payload": {"cmd": "ref_duration", "ref_duration": 10},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "15s",
                                "payload": {"cmd": "ref_duration", "ref_duration": 15},
                            }
                        }
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "ref_aspects"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def grok_img_keyboard(data: dict = None):
        data = data or {}
        grok_mode = data.get("grok_mode", "normal")  # default normal
        grok_resolution = data.get("grok_resolution", "720p")  # default max 720p

        def get_color(selected):
            return "primary" if selected else "secondary"

        buttons = []
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🎉 Fun",
                        "payload": {"cmd": "grok_param", "grok_mode": "fun"},
                    },
                    "color": get_color(grok_mode == "fun"),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "⚖️ Normal",
                        "payload": {"cmd": "grok_param", "grok_mode": "normal"},
                    },
                    "color": get_color(grok_mode == "normal"),
                },
            ]
        )
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🔥 Spicy",
                        "payload": {"cmd": "grok_param", "grok_mode": "spicy"},
                    },
                    "color": get_color(grok_mode == "spicy"),
                },
            ]
        )
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "480p",
                        "payload": {"cmd": "grok_param", "grok_resolution": "480p"},
                    },
                    "color": get_color(grok_resolution == "480p"),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "720p",
                        "payload": {"cmd": "grok_param", "grok_resolution": "720p"},
                    },
                    "color": get_color(grok_resolution == "720p"),
                },
            ]
        )
        buttons.append(
            [
                {
                    "action": {
                        "type": "text",
                        "label": "✅ Готово к промпту",
                        "payload": {"cmd": "grok_ready"},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Модели",
                        "payload": {"cmd": "ref_models"},
                    }
                },
            ]
        )
        return json.dumps({"inline": True, "buttons": buttons})

    @staticmethod
    def kling_config_kb(data: dict = None):
        data = data or {}
        kling_sound = data.get("kling_sound", True)

        def get_color(selected):
            return "primary" if selected else "secondary"

        buttons = [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🔊 Звук: Вкл",
                        "payload": {"cmd": "kling_param", "kling_sound": True},
                    },
                    "color": get_color(kling_sound),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🔇 Звук: Выкл",
                        "payload": {"cmd": "kling_param", "kling_sound": False},
                    },
                    "color": get_color(not kling_sound),
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "✅ Готово к промпту",
                        "payload": {"cmd": "kling_ready"},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Модели",
                        "payload": {"cmd": "ref_models"},
                    }
                },
            ],
        ]
        return json.dumps({"inline": True, "buttons": buttons})

    @staticmethod
    def seedance_config_kb(data: dict = None):
        data = data or {}
        resolution = data.get("seedance_resolution", "720p")
        generate_audio = data.get("seedance_audio", True)

        def get_color(selected):
            return "primary" if selected else "secondary"

        buttons = [
            [
                {
                    "action": {
                        "type": "text",
                        "label": "480p",
                        "payload": {
                            "cmd": "seedance_param",
                            "seedance_resolution": "480p",
                        },
                    },
                    "color": get_color(resolution == "480p"),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "720p",
                        "payload": {
                            "cmd": "seedance_param",
                            "seedance_resolution": "720p",
                        },
                    },
                    "color": get_color(resolution == "720p"),
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "🔊 Аудио: Вкл",
                        "payload": {"cmd": "seedance_param", "seedance_audio": True},
                    },
                    "color": get_color(generate_audio),
                },
                {
                    "action": {
                        "type": "text",
                        "label": "🔇 Аудио: Выкл",
                        "payload": {"cmd": "seedance_param", "seedance_audio": False},
                    },
                    "color": get_color(not generate_audio),
                },
            ],
            [
                {
                    "action": {
                        "type": "text",
                        "label": "✅ Готово к промпту",
                        "payload": {"cmd": "seedance_ready"},
                    }
                },
                {
                    "action": {
                        "type": "text",
                        "label": "⬅️ Модели",
                        "payload": {"cmd": "ref_models"},
                    }
                },
            ],
        ]
        return json.dumps({"inline": True, "buttons": buttons})

    @staticmethod
    def video_models_list():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⚡ Kling 3.0 std (15🍌)",
                                "payload": {"model": "kling_3_std"},
                            }
                        }
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "💎 Kling 3.0 pro (15🍌)",
                                "payload": {"model": "kling_3_pro"},
                            }
                        }
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "🌱 Seedance 1.5 (14🍌)",
                                "payload": {"model": "seedance_15"},
                            }
                        }
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "create_video"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def video_aspects():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "16:9",
                                "payload": {"aspect": "16:9"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "9:16",
                                "payload": {"aspect": "9:16"},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "1:1",
                                "payload": {"aspect": "1:1"},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "create_video"},
                            }
                        }
                    ],
                ],
            }
        )

    @staticmethod
    def video_durations():
        return json.dumps(
            {
                "inline": True,
                "buttons": [
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "5 сек",
                                "payload": {"duration": 5},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "10 сек",
                                "payload": {"duration": 10},
                            }
                        },
                        {
                            "action": {
                                "type": "text",
                                "label": "15 сек",
                                "payload": {"duration": 15},
                            }
                        },
                    ],
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": "⬅️ Назад",
                                "payload": {"cmd": "create_video"},
                            }
                        }
                    ],
                ],
            }
        )


class BananaBoomBot:
    def __init__(self):
        self.bot = Bot(Config.VK_TOKEN)
        self.db = Database()
        self.api_client = AIAPIClient()
        self.tbank = (
            TBankAPI(
                terminal_key=Config.TBANK_TERMINAL_KEY, password=Config.TBANK_SECRET_KEY
            )
            if Config.TBANK_TERMINAL_KEY
            else None
        )

        self.confirmation_code = None
        self.secret_key = None
        self._setup_handlers()

    async def vk_handler(self, request):
        try:
            data = await request.json()
        except:
            return web.Response(status=400)

        if data.get("type") == "confirmation":
            group_id = data.get("group_id")
            if group_id == 229102399:
                return web.Response(text="3d1929de")
            elif group_id == Config.VK_GROUP_ID:
                return web.Response(text=self.confirmation_code)
            elif group_id == 237065803:
                return web.Response(text="0d50c4ab")
            else:
                logging.warning(f"Unknown group_id {group_id} for confirmation")
                return web.Response(status=400)

        if data.get("secret") == self.secret_key:
            event_type = data.get("type")
            if event_type in ["message_read", "message_typing_state", "message_reply"]:
                return web.Response(text="ok")
            asyncio.create_task(self.bot.process_event(data))
            return web.Response(text="ok")

        return web.Response(status=403)

    def _setup_handlers(self):
        bot = self.bot

        @bot.on.message(CommandRule("start"))
        @bot.on.message(PayloadRule({"cmd": "main_menu"}))
        async def main_menu_handler(message: Message):
            user = self.db.get_or_create_user(message.from_id)
            if user["is_blocked"]:
                await message.answer(
                    f"⛔ Ваш аккаунт заблокирован.\nПричина: {user['block_reason']}"
                )
                return
            text = f"🍌 Banana Boom — создавай с AI!\n\n✅ Генерация артов: Пиши промпт — получай шедевр\n✅ Видео-продакшн: Делаю ролики из слов и фото\n\n🍌 Ваш баланс: {user['balance']} 🍌\n\n⚠️ Неприемлемый контент запрещён.\n\n👇 Попробуй!"
            await message.answer(text, keyboard=Keyboards.main_menu())
            self.db.clear_state(message.from_id)

        @bot.on.message(PayloadRule({"cmd": "create_video"}))
        async def create_video_handler(message: Message):
            user = self.db.get_or_create_user(message.from_id)
            text = "💰 Стоимость: от 14 🍌\n\nВведите промпт или выберите тип:"
            await message.answer(text, keyboard=Keyboards.video_options())
            self.db.set_state(
                message.from_id,
                UserState.VIDEO_WAITING_PROMPT.value,
                {"step": "choose_input"},
            )

        @bot.on.message(DBStateRule(self.db, UserState.VIDEO_WAITING_PROMPT.value))
        async def video_prompt_handler(message: Message):
            # Skip if model selection or cmd payload except ref_video
            try:
                payload_dict = json.loads(message.payload or "{}")
                if payload_dict.get("model"):
                    return
                cmd = payload_dict.get("cmd")
                if cmd == "ref_video":
                    await message.answer(
                        "🖼 Видео по референсам\\n\\n💰 Стоимость: 15-18 🍌\\n\\n📸 Отправьте референсные фото (1-9 шт, четкие изображения для стиля/персонажа):",
                        keyboard=Keyboards.regular_back("main_menu"),
                    )
                    self.db.set_state(
                        message.from_id,
                        UserState.REF_VIDEO_WAITING_REFS.value,
                        {"refs": []},
                    )
                    return
                if cmd:
                    return
            except:
                pass

            state, data = self.db.get_state(message.from_id)

            # Check if waiting for prompt after model
            if data.get("model"):
                model = data["model"]
                aspect = data.get("aspect", "16:9")
                cost = data.get("cost", 15)
                prompt_data = {"prompt": message.text, "aspect": aspect}
                user_id = message.from_id
                user = self.db.get_or_create_user(user_id)
                if user["balance"] < cost:
                    await message.answer(
                        f"❌ Недостаточно: {cost} vs {user['balance']}",
                        keyboard=Keyboards.main_menu(),
                    )
                    return
                task_id = self.db.create_task(
                    user_id, "video", model, json.dumps(prompt_data), cost, []
                )
                self.db.update_balance(
                    user_id, -cost, f"Видео #{task_id} {model} {aspect}"
                )
                await message.answer(
                    f"⏳ Задача #{task_id} создана! Ожидайте.",
                    keyboard=Keyboards.main_menu(),
                )
                asyncio.create_task(self._process_video_task(task_id))
                self.db.clear_state(user_id)
                return

            # Handle input type selection FIRST
            try:
                payload_dict = json.loads(message.payload or "{}")
            except:
                payload_dict = {}
            if "input" in payload_dict and payload_dict["input"] == "text":
                kb = Keyboards.regular_back("create_video")
                await message.answer("💭 Введите промпт для видео:", keyboard=kb)
                self.db.set_state(message.from_id, state, data)
                return

            # Handle text prompt
            if message.text:
                if message.text.startswith("/"):
                    await message.answer(
                        "⚠️ Команды типа /bugreport здесь не работают.\\n\\nВведите промпт для видео или используйте кнопки.",
                        keyboard=Keyboards.video_options(),
                    )
                    return
                data["prompt"] = message.text
                kb = Keyboards.video_models()
                await message.answer(
                    f"✅ Промпт: {data['prompt'][:50]}...\\nВыберите модель:",
                    keyboard=kb,
                )
                self.db.set_state(
                    message.from_id, UserState.VIDEO_WAITING_MODEL.value, data
                )
                return

        @bot.on.message(PayloadContainsRule("model"))
        async def video_model_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            state, data = self.db.get_state(message.from_id)
            if state == UserState.VIDEO_WAITING_MODEL.value:
                model = payload["model"]
                cost = Config.PRICES.get(f"video_{model}", 15)
                data["model"] = model
                data["cost"] = cost
                await message.answer(
                    f"✅ Модель: {model} ({cost}🍌)\\nВыберите соотношение сторон:",
                    keyboard=Keyboards.video_aspects(),
                )
                self.db.set_state(
                    message.from_id, UserState.VIDEO_WAITING_ASPECT.value, data
                )
                return

            # legacy flow
            model = payload["model"]
            aspect = payload.get("aspect", "16:9")
            cost = payload["cost"]
            prompt = data.get("prompt", "")
            data["model"] = model
            data["aspect"] = aspect
            data["cost"] = cost
            if not prompt:
                kb = Keyboards.regular_back("create_video")
                await message.answer(
                    f"✅ Модель: {model} {aspect} ({cost}🍌)\\nВведите промпт:",
                    keyboard=kb,
                )
                self.db.set_state(message.from_id, state, data)
                return
            prompt_data = {"prompt": prompt, "aspect": aspect}
            user_id = message.from_id
            user = self.db.get_or_create_user(user_id)
            if user["balance"] < cost:
                await message.answer(
                    f"❌ Недостаточно 🍌: {cost} vs {user['balance']}",
                    keyboard=Keyboards.main_menu(),
                )
                return
            task_id = self.db.create_task(
                user_id,
                "video",
                model,
                json.dumps(prompt_data),
                cost,
                data.get("photos", []),
            )
            self.db.update_balance(user_id, -cost, f"Видео #{task_id} {model} {aspect}")
            await message.answer(
                f"⏳ Задача #{task_id} создана! Ожидайте.",
                keyboard=Keyboards.main_menu(),
            )
            asyncio.create_task(self._process_video_task(task_id))
            self.db.clear_state(user_id)

        # Motion Control
        @bot.on.message(PayloadRule({"cmd": "motion_control"}))
        async def motion_control_handler(message: Message):
            await message.answer(
                "Выберите тип Motion Control:",
                keyboard=Keyboards.motion_control_types(),
            )

        @bot.on.message(PayloadContainsRule("type"))
        async def mc_type_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            mc_type = payload["type"]
            cost = payload["cost"]
            await message.answer(
                f"📸 Отправьте фото персонажа.\nТип: {mc_type} ({cost} 🍌)",
                keyboard=Keyboards.regular_back("motion_control"),
            )
            self.db.set_state(
                message.from_id,
                UserState.MC_WAITING_CHARACTER_PHOTO.value,
                {"type": mc_type, "cost": cost},
            )

        @bot.on.message(
            DBStateRule(self.db, UserState.MC_WAITING_CHARACTER_PHOTO.value)
        )
        async def mc_photo_handler(message: Message):
            if message.attachments and any(att.photo for att in message.attachments):
                photo_att = next(
                    (att for att in message.attachments if att.photo), None
                )
                if photo_att:
                    photo_obj = photo_att.photo
                    photo_url = photo_obj.sizes[-1].url if photo_obj.sizes else None
                    if photo_url:
                        state, data = self.db.get_state(message.from_id)
                        data["character_photo"] = photo_url
                        await message.answer(
                            "💭 Введите промпт для motion control (описание движения персонажа):",
                            keyboard=Keyboards.regular_back("motion_control"),
                        )
                        self.db.set_state(
                            message.from_id, UserState.MC_WAITING_PROMPT.value, data
                        )
                        return
            await message.answer(
                "❌ Неверное фото. Отправьте четкое фото персонажа (голова, плечи, торс, JPEG/PNG/JPG)."
            )

        @bot.on.message(
            DBStateRule(self.db, UserState.MC_WAITING_PROMPT.value), TextExistsRule()
        )
        async def mc_prompt_handler(message: Message):
            prompt = message.text
            state, data = self.db.get_state(message.from_id)
            data["prompt"] = prompt
            await message.answer(
                "🎥 Отправьте видео с желаемым движением (3-30 сек, MP4, показывает голову, плечи, торс).",
                keyboard=Keyboards.regular_back("motion_control"),
            )
            self.db.set_state(
                message.from_id, UserState.MC_WAITING_MOTION_VIDEO.value, data
            )

        @bot.on.message(DBStateRule(self.db, UserState.MC_WAITING_MOTION_VIDEO.value))
        async def mc_video_handler(message: Message):
            video_url = None
            video_att = None
            doc_att = None

            # Check for video attachment
            if any(att.video for att in message.attachments):
                video_att = next(
                    (att for att in message.attachments if att.video), None
                )
                video_obj = video_att.video if video_att else None
                if video_obj:
                    if getattr(video_obj, "sizes", None) and video_obj.sizes:
                        size = max(
                            video_obj.sizes,
                            key=lambda s: (s.width or 0) * (s.height or 0),
                        )
                        video_url = size.url
                    elif hasattr(video_obj, "player") and video_obj.player:
                        video_url = video_obj.player
                    else:
                        # Get direct MP4 URL via VK API
                        owner_id = getattr(video_obj, "owner_id", 0)
                        vid_id = getattr(video_obj, "id", 0)
                        acc_key = getattr(video_obj, "access_key", "")
                        if owner_id and vid_id:
                            video_api_params = f"{owner_id}_{vid_id}"
                            if acc_key:
                                video_api_params += f"_{acc_key}"
                            try:
                                video_info = await self.bot.api.video.get(
                                    videos=video_api_params
                                )
                                if video_info.items:
                                    files = video_info.items[0].files
                                    # Prefer external or highest MP4
                                    if hasattr(files, "external") and files.external:
                                        video_url = files.external
                                    elif hasattr(files, "mp4_720") and files.mp4_720:
                                        video_url = files.mp4_720
                                    elif hasattr(files, "mp4_480") and files.mp4_480:
                                        video_url = files.mp4_480
                                    elif hasattr(files, "mp4_360") and files.mp4_360:
                                        video_url = files.mp4_360
                                    else:
                                        raise ValueError("No MP4 files available")
                                    logging.info(
                                        f"mc_video_handler direct video from API: {video_url}"
                                    )
                                else:
                                    raise ValueError("No video info")
                            except Exception as e:
                                logging.error(f"Video API error: {e}")
                                await message.answer(
                                    "❌ Не удалось получить прямую ссылку на видео. Попробуйте загрузить MP4 как документ."
                                )
                                return
                        else:
                            await message.answer("❌ Неверное видео.")
                            return

            # Check for doc MP4 attachment (direct file)
            elif any(att.doc and att.doc.ext == "mp4" for att in message.attachments):
                doc_att = next(
                    (
                        att
                        for att in message.attachments
                        if att.doc and att.doc.ext == "mp4"
                    ),
                    None,
                )
                if doc_att:
                    # Download VK doc to local temp
                    temp_dir = Path("uploads")
                    temp_dir.mkdir(exist_ok=True)
                    local_path = temp_dir / f"motion_video_{int(time.time())}.mp4"
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(doc_att.doc.url) as resp:
                                if resp.status == 200:
                                    content = await resp.read()
                                    with open(local_path, "wb") as f:
                                        f.write(content)
                                    logging.info(f"Downloaded VK doc to {local_path}")
                                else:
                                    raise ValueError(f"Download failed: {resp.status}")
                        input_data["local_video_path"] = str(local_path)
                    except Exception as e:
                        logging.error(f"Download VK doc failed: {e}")
                        await message.answer(
                            "❌ Не удалось скачать видео. Попробуйте другое."
                        )
                        return
                    video_url = doc_att.doc.url  # fallback, but use local
                    logging.info(
                        f"mc_video_handler VK doc: {video_url}, local: {local_path}"
                    )

            if not video_url:
                await message.answer(
                    "❌ Видео не распознано. Отправьте MP4 файл (doc) или VK видео напрямую."
                )
                return

            state, data = self.db.get_state(message.from_id)
            cost = data["cost"]
            user = self.db.get_or_create_user(message.from_id)
            if user["balance"] < cost:
                await message.answer("❌ Недостаточно средств.")
                return
            mc_type = data["type"]
            mode = "720p" if mc_type == "standard" else "1080p"
            input_data = {
                "prompt": data["prompt"],
                "input_urls": [data["character_photo"]],
                "video_urls": [video_url],
                "character_orientation": "video",
                "mode": mode,
            }
            task_id = self.db.create_task(
                message.from_id,
                "motion_control",
                mc_type,
                json.dumps(input_data),
                cost,
                [],
            )
            self.db.update_balance(
                message.from_id, -cost, f"Motion Control #{task_id} {mc_type}"
            )
            await message.answer(f"⏳ #{task_id} Motion Control запущен!")
            asyncio.create_task(self._process_motion_task(task_id))
            self.db.clear_state(message.from_id)

        # Photo
        @bot.on.message(PayloadRule({"cmd": "create_photo"}))
        async def create_photo_handler(message: Message):
            balance = self.db.get_balance(message.from_id)
            await message.answer(
                f"🖼 Создание фото\n\n🍌 Баланс: {balance} 🍌\n\nШаг 1: Загрузка референсов (опционально, до 14)\n\nПосле - 'Продолжить' или 'Пропустить'",
                keyboard=Keyboards.photo_creation_step(),
            )
            self.db.set_state(
                message.from_id,
                UserState.PHOTO_WAITING_REFERENCES.value,
                {"photos": []},
            )

        @bot.on.message(DBStateRule(self.db, UserState.PHOTO_WAITING_REFERENCES.value))
        async def photo_references_handler(message: Message):
            state, data = self.db.get_state(message.from_id)

            if message.payload:
                payload = json.loads(message.payload or "{}")
                action = payload.get("action")

                if action == "skip_refs":
                    has_refs = False
                elif action == "continue_refs":
                    has_refs = len(data.get("photos", [])) > 0
                else:
                    return

                kb = Keyboards.photo_models_kb(has_refs)
                msg = (
                    "✅ Референсы готовы.\n\nВыберите модель:"
                    if action == "continue_refs"
                    else "✅ Референсы пропущены.\n\nВыберите модель:"
                )
                await message.answer(msg, keyboard=kb)
                self.db.set_state(
                    message.from_id, UserState.PHOTO_WAITING_MODEL.value, data
                )
                return

            if message.attachments:
                photos = [att for att in message.attachments if att.photo]
                if photos:
                    for photo in photos:
                        photo_obj = photo.photo
                        photo_url = photo_obj.sizes[-1].url if photo_obj.sizes else None
                        if photo_url and len(data["photos"]) < 14:
                            data.setdefault("photos", []).append(photo_url)

                    await message.answer(
                        f"📸 Загружено: {len(data['photos'])}/14\nОтправьте ещё фото или кнопки",
                        keyboard=Keyboards.photo_creation_step(),
                    )
                    self.db.set_state(message.from_id, state, data)
                    return

            await message.answer("Отправьте фото или используйте кнопки.")

        @bot.on.message(
            PayloadContainsRule("photo_model"),
            DBStateRule(self.db, UserState.PHOTO_WAITING_MODEL.value),
        )
        async def photo_model_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            photo_model = payload["photo_model"]
            cost = payload["cost"]
            state, data = self.db.get_state(message.from_id)
            data["photo_model"] = photo_model
            data["cost"] = cost
            model_labels = {
                "nano_banana_2": "Nano Banana 2",
                "nano_banana_pro": "Nano Banana Pro",
                "seedream_text": "Seedream T2I",
                "seedream_edit": "Seedream Edit",
            }
            model_label = model_labels.get(
                photo_model, photo_model.replace("_", " ").title()
            )
            kb = Keyboards.photo_aspects_kb()
            self.db.set_state(
                message.from_id, UserState.PHOTO_WAITING_ASPECT.value, data
            )
            await message.answer(
                f"✅ Модель: {model_label} • {cost}🍌\n\nВыберите соотношение сторон:",
                keyboard=kb,
            )

        @bot.on.message(
            PayloadContainsRule("aspect"),
            DBStateRule(self.db, UserState.PHOTO_WAITING_ASPECT.value),
        )
        async def photo_aspect_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            aspect = payload["aspect"]
            state, data = self.db.get_state(message.from_id)
            data["aspect"] = aspect
            photo_model = data["photo_model"]
            cost = data["cost"]
            model_labels = {
                "nano_banana_2": "Nano Banana 2",
                "nano_banana_pro": "Nano Banana Pro",
                "seedream_text": "Seedream T2I",
                "seedream_edit": "Seedream Edit",
            }
            model_label = model_labels.get(
                photo_model, photo_model.replace("_", " ").title()
            )
            self.db.set_state(
                message.from_id, UserState.PHOTO_WAITING_PROMPT.value, data
            )
            await message.answer(
                f"✅ Модель: {model_label} • {aspect} {cost}🍌\n\n💭 Введите промпт:",
                keyboard=Keyboards.regular_back("create_photo"),
            )

        @bot.on.message(
            DBStateRule(self.db, UserState.PHOTO_WAITING_PROMPT.value), TextExistsRule()
        )
        async def photo_prompt_handler(message: Message):
            state, data = self.db.get_state(message.from_id)
            photo_model = data["photo_model"]
            aspect = data["aspect"]
            cost = data["cost"]
            photos = data.get("photos", [])
            prompt_data = {"prompt": message.text, "aspect": aspect}
            prompt_json = json.dumps(prompt_data)
            user_id = message.from_id
            user = self.db.get_or_create_user(user_id)
            if user["balance"] < cost:
                await message.answer(
                    f"❌ Недостаточно: нужно {cost}, у вас {user['balance']} 🍌",
                    keyboard=Keyboards.main_menu(),
                )
                self.db.clear_state(user_id)
                return

            task_id = self.db.create_task(
                user_id, "photo", photo_model, prompt_json, cost, photos
            )
            self.db.update_balance(user_id, -cost, f"Фото #{task_id} {photo_model}")
            await message.answer(
                f"🚀 Задача #{task_id} ({photo_model} {aspect}) запущена!",
                keyboard=Keyboards.main_menu(),
            )
            asyncio.create_task(self._process_photo_task(task_id))
            self.db.clear_state(user_id)

        # Устаревший handler для aspect, теперь не используется
        # @bot.on.message(
        #     PayloadContainsRule("aspect"),
        #     DBStateRule(self.db, UserState.PHOTO_WAITING_ASPECT.value),
        # )
        # async def photo_aspect_handler(message: Message):
        #     ...

        # Анализ фото
        @bot.on.message(PayloadRule({"cmd": "photo_analysis"}))
        async def photo_analysis_handler(message: Message):
            text = f"📸 Фото→Промпт (бесплатно)\n\nОтправьте фото для анализа."
            await message.answer(text, keyboard=Keyboards.regular_back("main_menu"))
            self.db.set_state(
                message.from_id, UserState.ANALYSIS_WAITING_PHOTO.value, {}
            )

        @bot.on.message(DBStateRule(self.db, UserState.ANALYSIS_WAITING_PHOTO.value))
        async def photo_analysis_upload_handler(message: Message):
            if not message.attachments or not any(
                att.photo for att in message.attachments
            ):
                await message.answer("❌ Отправьте фото.")
                return

            photo_att = next((att for att in message.attachments if att.photo), None)
            if photo_att:
                try:
                    photo_obj = photo_att.photo
                    valid_sizes = [
                        s
                        for s in photo_obj.sizes
                        if hasattr(s, "type") and s.type != "base"
                    ]
                    if valid_sizes:
                        photo_url = valid_sizes[-1].url
                    else:
                        photo_url = photo_obj.sizes[-1].url if photo_obj.sizes else None
                except Exception as e:
                    logging.error(f"Analysis photo error: {e}")
                    photo_url = None
            else:
                photo_url = None

            await message.answer("🔍 Анализирую фото...")

            async with self.api_client:
                prompt = await self.api_client.analyze_photo(photo_url)

            await message.answer(
                f"✅ Готовый промпт:\\n\\n<code>{prompt}</code>\\n\\nИспользуйте для генерации!",
                keyboard=Keyboards.main_menu(),
            )
            self.db.clear_state(message.from_id)

        # Пополнение и поддержка
        @bot.on.message(PayloadRule({"cmd": "top_up"}))
        async def top_up_handler(message: Message):
            balance = self.db.get_balance(message.from_id)
            kb = json.dumps(
                {
                    "inline": True,
                    "buttons": [
                        [
                            {
                                "action": {
                                    "type": "text",
                                    "label": "30 🍌 — 250 ₽",
                                    "payload": {"topup": 250},
                                }
                            }
                        ],
                        [
                            {
                                "action": {
                                    "type": "text",
                                    "label": "40 🍌 — 400 ₽",
                                    "payload": {"topup": 400},
                                }
                            }
                        ],
                        [
                            {
                                "action": {
                                    "type": "text",
                                    "label": "100 🍌 — 700 ₽",
                                    "payload": {"topup": 700},
                                }
                            }
                        ],
                        [
                            {
                                "action": {
                                    "type": "text",
                                    "label": "200 🍌 — 1400 ₽",
                                    "payload": {"topup": 1400},
                                }
                            }
                        ],
                        [
                            {
                                "action": {
                                    "type": "text",
                                    "label": "⬅️ Назад",
                                    "payload": {"cmd": "main_menu"},
                                }
                            }
                        ],
                    ],
                }
            )
            await message.answer(
                f"💰 Пополнить баланс\n\n🍌 Текущий: {balance}\n\nВыберите пакет:",
                keyboard=kb,
                parse_mode="HTML",
            )

        @bot.on.message(PayloadRule({"cmd": "support"}))
        async def support_handler(message: Message):
            await message.answer(
                f"🔧 Поддержка\n\n@support_manager\n\nКанал: @banana_boom_channel",
                keyboard=Keyboards.main_menu(),
            )

        @bot.on.message(PayloadContainsRule("topup"), blocking=True)
        async def topup_package_handler(message: Message):
            try:
                payload = json.loads(message.payload or "{}")
                rub = int(payload["topup"])
            except:
                await message.answer("❌ Неверный формат.")
                return

            bananas = Config.PACKAGES.get(rub, 0)
            if not bananas:
                await message.answer("❌ Неверная сумма.")
                return

            user_id = message.from_id
            order_id = f"pay_{user_id}_{int(time.time())}"
            self.db.create_pending_payment(user_id, order_id, rub)

            desc = f"Пополнение {bananas} 🍌"
            request = InitPaymentRequest(
                Amount=rub * 100,
                OrderId=order_id,
                Description=desc,
                NotificationURL=f"{Config.WEBHOOK_HOST}/webhook/tbank",
                SuccessURL=f"{Config.WEBHOOK_HOST}/pay_success?order_id={order_id}",
                FailURL=f"{Config.WEBHOOK_HOST}/pay_fail?order_id={order_id}",
            )
            result = self.tbank.init_payment(request)

            if result.success:
                payment_url = result.payment_url
                self.db.update_payment_tbank_id(
                    self.db.get_payment_by_order_id(order_id)["id"], result.payment_id
                )

                await message.answer(
                    f"💳 Оплата {rub} ₽ за {bananas} 🍌\n\n[Перейти к оплате]({payment_url})\n\nПосле оплаты баланс обновится автоматически.",
                    parse_mode="Markdown",
                    keyboard=Keyboards.main_menu(),
                )
            else:
                await message.answer(
                    "❌ Ошибка создания платежа. Попробуйте позже.",
                    keyboard=Keyboards.main_menu(),
                )
            self.db.clear_state(message.from_id)

        @bot.on.message(PayloadRule({"cmd": "ref_video"}))
        async def ref_video_handler(message: Message):
            await message.answer(
                "🖼 Видео по референсам\\n\\n💰 Стоимость: 15-18 🍌\\n\\n📸 Отправьте референсные фото (0-9 шт, четкие изображения для стиля/персонажа, опционально):\\n\\n👇 Кнопки ниже",
                keyboard=Keyboards.ref_creation_step(),
            )
            self.db.set_state(
                message.from_id,
                UserState.REF_VIDEO_WAITING_REFS.value,
                {"refs": []},
            )

        @bot.on.message(DBStateRule(self.db, UserState.REF_VIDEO_WAITING_REFS.value))
        async def ref_refs_handler(message: Message):
            state, data = self.db.get_state(message.from_id)
            if message.payload:
                try:
                    payload = json.loads(message.payload)
                    action = payload.get("action")
                    if action in ("refs_ready", "skip_refs"):
                        ref_count = len(data.get("refs", []))
                        self.db.set_state(
                            message.from_id,
                            UserState.REF_VIDEO_CONFIG.value,
                            data,
                        )
                        try:
                            await message.answer(
                                f"✅ Референсов: {ref_count}\\nВыберите модель, длительность, соотношение:",
                                keyboard=Keyboards.ref_combined_kb(data),
                            )
                        except Exception as e:
                            logging.error(f"Failed to send ref menu: {e}")
                            await message.answer(
                                f"✅ Референсов: {ref_count}\\nВыберите модель, длительность, соотношение:",
                            )
                        return
                except:
                    pass

            if message.attachments:
                photos = [att for att in message.attachments if att.photo]
                added = 0
                for photo in photos:
                    if len(data.get("refs", [])) < 9:
                        photo_url = (
                            photo.photo.sizes[-1].url if photo.photo.sizes else None
                        )
                        if photo_url:
                            data.setdefault("refs", []).append(photo_url)
                            added += 1
                count = len(data["refs"])
                kb = Keyboards.ref_creation_step()
                kb_buttons = json.loads(kb)
                kb_buttons["buttons"].insert(
                    0,
                    [
                        {
                            "action": {
                                "type": "text",
                                "label": f"✅ Готово ({count}/9)",
                                "payload": {"action": "refs_ready"},
                            }
                        }
                    ],
                )
                kb = json.dumps(kb_buttons)
                await message.answer(
                    f"✅ Добавлено {added} фото ({count}/9). Еще или готово:",
                    keyboard=kb,
                )
                self.db.set_state(message.from_id, state, data)
                return
            await message.answer("📤 Отправьте фото или кнопки.")

        @bot.on.message(
            PayloadContainsRule("ref_model"),
            DBStateRule(self.db, UserState.REF_VIDEO_CONFIG.value),
        )
        async def ref_model_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            state, data = self.db.get_state(message.from_id)
            data["ref_model"] = payload["ref_model"]
            data["model"] = payload["ref_model"]
            if "kling_mode" in payload:
                data["kling_mode"] = payload["kling_mode"]
            self.db.set_state(message.from_id, state, data)
            await message.answer(
                "Параметры обновлены. Выберите недостающее:",
                keyboard=Keyboards.ref_combined_kb(data),
            )
            if all(k in data for k in ["ref_model", "aspect", "duration"]):
                ref_model = data["ref_model"]
                cost = Config.PRICES.get(f"video_{data['model']}", 15)
                if ref_model == "grok":
                    await message.answer(
                        "🤖 Grok настройки видео:",
                        keyboard=Keyboards.grok_img_keyboard(data),
                    )
                elif ref_model == "kling3":
                    await message.answer(
                        "⚡ Kling настройки видео:",
                        keyboard=Keyboards.kling_config_kb(data),
                    )
                elif ref_model == "seedance2":
                    await message.answer(
                        "🌿 Seedance2 настройки видео:",
                        keyboard=Keyboards.seedance_config_kb(data),
                    )

        @bot.on.message(
            PayloadContainsRule("ref_aspect"),
            DBStateRule(self.db, UserState.REF_VIDEO_CONFIG.value),
        )
        async def ref_aspect_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            state, data = self.db.get_state(message.from_id)
            data["aspect"] = payload["ref_aspect"]
            self.db.set_state(message.from_id, state, data)
            await message.answer(
                "Параметры обновлены. Выберите недостающее:",
                keyboard=Keyboards.ref_combined_kb(data),
            )
            if all(k in data for k in ["ref_model", "aspect", "duration"]):
                ref_model = data["ref_model"]
                cost = Config.PRICES.get(f"video_{data['model']}", 15)
                if ref_model == "grok":
                    await message.answer(
                        "🤖 Grok настройки видео:",
                        keyboard=Keyboards.grok_img_keyboard(data),
                    )
                elif ref_model == "kling3":
                    await message.answer(
                        "⚡ Kling настройки видео:",
                        keyboard=Keyboards.kling_config_kb(data),
                    )
                elif ref_model == "seedance2":
                    await message.answer(
                        "🌿 Seedance2 настройки видео:",
                        keyboard=Keyboards.seedance_config_kb(data),
                    )

        @bot.on.message(
            PayloadContainsRule("ref_duration"),
            DBStateRule(self.db, UserState.REF_VIDEO_CONFIG.value),
        )
        async def ref_duration_handler(message: Message):
            payload = json.loads(message.payload or "{}")
            state, data = self.db.get_state(message.from_id)
            data["duration"] = payload["ref_duration"]
            self.db.set_state(message.from_id, state, data)
            await message.answer(
                "Параметры обновлены. Выберите недостающее:",
                keyboard=Keyboards.ref_combined_kb(data),
            )
            if all(k in data for k in ["ref_model", "aspect", "duration"]):
                ref_model = data["ref_model"]
                cost = Config.PRICES.get(f"video_{data['model']}", 15)
                if ref_model == "grok":
                    await message.answer(
                        "🤖 Grok настройки видео:",
                        keyboard=Keyboards.grok_img_keyboard(data),
                    )
                elif ref_model == "kling3":
                    await message.answer(
                        "⚡ Kling настройки видео:",
                        keyboard=Keyboards.kling_config_kb(data),
                    )
                elif ref_model == "seedance2":
                    await message.answer(
                        "🌿 Seedance2 настройки видео:",
                        keyboard=Keyboards.seedance_config_kb(data),
                    )

        @bot.on.message(
            PayloadContainsRule("cmd"),
            DBStateRule(self.db, UserState.REF_VIDEO_CONFIG.value),
        )
        async def ref_config_handler(message: Message):
            try:
                payload_dict = json.loads(message.payload or "{}")
                cmd = payload_dict.get("cmd")
                payload = payload_dict
            except:
                return
            state, data = self.db.get_state(message.from_id)

            ref_model = data.get("ref_model")

            if cmd == "grok_param":
                if "grok_mode" in payload:
                    data["grok_mode"] = payload["grok_mode"]
                if "grok_resolution" in payload:
                    data["grok_resolution"] = payload["grok_resolution"]
                self.db.set_state(message.from_id, state, data)
                mode = data.get("grok_mode", "normal")
                res = data.get("grok_resolution", "720p")
                await message.answer(
                    f"🤖 Grok Img2Video\nMode: {mode}\nResolution: {res}\n\nВыберите:",
                    keyboard=Keyboards.grok_img_keyboard(data),
                )
                return

            if cmd == "grok_ready":
                required = ["ref_model", "aspect", "duration"]
                if ref_model != "grok" or not all(k in data for k in required):
                    await message.answer(
                        "⚠️ Выберите модель Grok, aspect и duration сначала!",
                        keyboard=Keyboards.grok_img_keyboard(data),
                    )
                    return
                cost = Config.PRICES.get("video_grok_img2video", 20)
                mode = data.get("grok_mode", "normal")
                res = data.get("grok_resolution", "720p")
                await message.answer(
                    f"✅ Grok Img2Video {data['aspect']} {data['duration']}s {mode} {res} ({cost}🍌)\n\n📝 Введите промпт:",
                    keyboard=Keyboards.regular_back("main_menu"),
                )
                return

            if cmd == "kling_param":
                if "kling_sound" in payload:
                    data["kling_sound"] = payload["kling_sound"]
                self.db.set_state(message.from_id, state, data)
                sound_str = "Вкл" if data.get("kling_sound", True) else "Выкл"
                await message.answer(
                    f"⚡ Kling 3.0\nЗвук: {sound_str}\n\nВыберите:",
                    keyboard=Keyboards.kling_config_kb(data),
                )
                return

            if cmd == "kling_ready":
                required = ["ref_model", "aspect", "duration"]
                if ref_model != "kling3" or not all(k in data for k in required):
                    await message.answer(
                        "⚠️ Выберите Kling, aspect и duration сначала!",
                        keyboard=Keyboards.kling_config_kb(data),
                    )
                    return
                cost = Config.PRICES.get("video_kling3", 15)
                sound_str = "Вкл" if data.get("kling_sound", True) else "Выкл"
                await message.answer(
                    f"✅ Kling {data['aspect']} {data['duration']}s Звук: {sound_str} ({cost}🍌)\n\n📝 Введите промпт:",
                    keyboard=Keyboards.regular_back("main_menu"),
                )
                return

            if cmd == "seedance_param":
                if "seedance_resolution" in payload:
                    data["seedance_resolution"] = payload["seedance_resolution"]
                if "seedance_audio" in payload:
                    data["seedance_audio"] = payload["seedance_audio"]
                self.db.set_state(message.from_id, state, data)
                res = data.get("seedance_resolution", "720p")
                audio_str = "Вкл" if data.get("seedance_audio", True) else "Выкл"
                await message.answer(
                    f"🌿 Seedance2\nResolution: {res}\nАудио: {audio_str}\n\nВыберите:",
                    keyboard=Keyboards.seedance_config_kb(data),
                )
                return

            if cmd == "seedance_ready":
                required = ["ref_model", "aspect", "duration"]
                if ref_model != "seedance2" or not all(k in data for k in required):
                    await message.answer(
                        "⚠️ Выберите Seedance2, aspect и duration сначала!",
                        keyboard=Keyboards.seedance_config_kb(data),
                    )
                    return
                cost = Config.PRICES.get("video_seedance2", 17)
                res = data.get("seedance_resolution", "720p")
                audio_str = "Вкл" if data.get("seedance_audio", True) else "Выкл"
                await message.answer(
                    f"✅ Seedance2 {data['aspect']} {data['duration']}s {res} Аудио: {audio_str} ({cost}🍌)\n\n📝 Введите промпт:",
                    keyboard=Keyboards.regular_back("main_menu"),
                )
                return

            if cmd == "ref_models":
                await message.answer(
                    "Выберите модель:",
                    keyboard=Keyboards.ref_models_kb(),
                )
                return

        @bot.on.message(
            DBStateRule(self.db, UserState.REF_VIDEO_CONFIG.value), TextExistsRule()
        )
        async def ref_video_prompt_handler(message: Message):
            _, data = self.db.get_state(message.from_id)
            required = ["ref_model", "aspect", "duration"]
            if not all(k in data for k in required):
                await message.answer(
                    "⚠️ Сначала выберите все параметры (модель, соотношение, длительность)!",
                    keyboard=Keyboards.ref_combined_kb(data),
                )
                return

            user_prompt = message.text
            model = data["model"]
            ref_model = data["ref_model"]
            cost = Config.PRICES.get(f"video_{model}", 15)
            user_id = message.from_id
            user = self.db.get_or_create_user(user_id)
            if user["balance"] < cost:
                await message.answer(
                    f"❌ Недостаточно бананов: нужно {cost}, у вас {user['balance']}",
                    keyboard=Keyboards.main_menu(),
                )
                self.db.clear_state(user_id)
                return

            task_data = {
                "user_prompt": user_prompt,
                "aspect": data["aspect"],
                "duration": data["duration"],
                "refs": data["refs"],
            }
            if ref_model == "grok":
                task_data["grok_mode"] = data.get("grok_mode", "normal")
                task_data["grok_resolution"] = data.get("grok_resolution", "720p")
            elif ref_model == "kling3":
                task_data["kling_mode"] = data.get("kling_mode", "std")
                task_data["kling_sound"] = data.get("kling_sound", True)
            elif ref_model == "seedance2":
                task_data["seedance_resolution"] = data.get(
                    "seedance_resolution", "720p"
                )
                task_data["seedance_audio"] = data.get("seedance_audio", True)
            task_id = self.db.create_task(
                user_id, "ref_video", model, json.dumps(task_data), cost
            )
            self.db.update_balance(user_id, -cost, f"Ref видео #{task_id} {model}")
            await message.answer(
                f"🚀 Задача #{task_id} ({model} {data['aspect']} {data['duration']}s) запущена!",
                keyboard=Keyboards.main_menu(),
            )
            asyncio.create_task(self._process_ref_video_task(task_id))
            self.db.clear_state(user_id)

        @bot.on.message()
        async def unknown_handler(message: Message):
            await message.answer(
                "Не понял. Используйте меню:", keyboard=Keyboards.main_menu()
            )

    async def _send_task_result(self, task_id: int):
        try:
            details = self.db.get_task_details(task_id)
            if not details:
                logging.warning(f"No details for task {task_id}")
                return
            user_id = details["user_id"]
            logging.info(
                f"Sending result for task {task_id} to user {user_id}, status: {details['status']}"
            )
            if details["status"] == "completed":
                result_url = details["result_url"] or "Результат не найден"
                msg = f"✅ Задача #{task_id} готова!\nРезультат: {result_url}"
            elif details["status"] == "failed":
                cost = details["cost"] or 0
                error_msg = details["error_message"] or "Неизвестная ошибка"
                reason = f"Возврат за проваленную задачу #{task_id}: {error_msg[:100]}"
                self.db.update_balance(user_id, cost, reason)
                msg = f"❌ Задача #{task_id} провалилась.\n\nОшибка: {error_msg}\n\n💰 Вернули {cost} 🍌 на баланс."
            else:
                logging.info(
                    f"Task {task_id} status {details['status']}, skipping notify"
                )
                return
            await self.bot.api.messages.send(
                user_id=user_id,
                message=msg,
                keyboard=Keyboards.main_menu(),
                random_id=int(time.time()),
            )
            logging.info(f"Sent result notification for task {task_id}")
        except Exception as e:
            logging.error(f"Failed to send task {task_id} result: {e}")

    async def _process_video_task(self, task_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT model, prompt FROM generation_tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        model, prompt_str = row
        try:
            prompt_data = json.loads(prompt_str)
            user_prompt = prompt_data["prompt"]
            aspect = prompt_data["aspect"]
            self.db.update_task_status(task_id, "processing")

            # Map model to KIE model and params
            if model == "kling_3_std":
                kie_model = "kling-3.0/video"
                mode = "std"
            elif model == "kling_3_pro":
                kie_model = "kling-3.0/video"
                mode = "pro"
            elif "seedance_15" in model:
                kie_model = "bytedance/seedance-1.5"
                mode = None
            else:
                raise ValueError(f"Unknown video model: {model}")

            input_data = {
                "prompt": user_prompt,
                "aspect_ratio": aspect,
                "duration": 5,
                "sound": True,
                "nsfw_checker": False,
            }
            if mode:
                input_data["mode"] = mode

            api_task_id = await self.api_client.create_kie_task(
                kie_model, input_data, Config.KLING_API_KEY
            )
            self.db.update_task_status(task_id, "processing", api_task_id=api_task_id)
        except Exception as e:
            self.db.update_task_status(task_id, "failed", error_message=str(e))
            logging.error(f"Video task {task_id} failed: {e}")
            await self._send_task_result(task_id)

    async def _process_motion_task(self, task_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT model, prompt FROM generation_tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        mc_type, prompt_json = row
        input_data = json.loads(prompt_json)
        try:
            self.db.update_task_status(task_id, "processing")
            # Upload VK URLs directly to KIE
            photo_url = input_data["input_urls"][0]
            video_url = input_data["video_urls"][0]
            logging.info(
                f"Motion task #{task_id}: photo={photo_url[:100]}..., video={video_url[:100]}..."
            )

            kie_photo_url = await self.api_client.upload_url_to_kie(
                photo_url, Config.KLING_API_KEY, "motioncontrol"
            )
            if "local_video_path" in input_data:
                kie_video_url = await self.api_client.upload_file_to_kie(
                    input_data["local_video_path"],
                    Config.KLING_API_KEY,
                    "motioncontrol",
                )
                # Clean up local file
                os.remove(input_data["local_video_path"])
            else:
                kie_video_url = await self.api_client.upload_url_to_kie(
                    video_url, Config.KLING_API_KEY, "motioncontrol"
                )
            logging.info(
                f"Motion task #{task_id}: kie_photo={kie_photo_url[:100]}..., kie_video={kie_video_url[:100]}..."
            )

            # Update input_data with KIE URLs
            input_data["input_urls"] = [kie_photo_url]
            input_data["video_urls"] = [kie_video_url]

            # Create KIE task
            model = "kling-2.6/motion-control"
            api_task_id = await self.api_client.create_kie_task(
                model, input_data, Config.KLING_API_KEY
            )
            self.db.update_task_status(task_id, "processing", api_task_id=api_task_id)
        except Exception as e:
            self.db.update_task_status(task_id, "failed", error_message=str(e))
            logging.error(f"Motion task {task_id} failed: {e}")
            await self._send_task_result(task_id)

    async def _process_photo_task(self, task_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT model, prompt, reference_photos FROM generation_tasks WHERE task_id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        model_name, prompt_json_str, ref_json = row
        photos = json.loads(ref_json or "[]")
        prompt_json = json.loads(prompt_json_str)
        user_prompt = prompt_json["prompt"]
        aspect = prompt_json.get("aspect", "1:1")
        try:
            self.db.update_task_status(task_id, "processing")
            api_key = Config.KLING_API_KEY
            if model_name == "nano_banana_2":
                kie_model = "nano-banana-2"
                input_data = {
                    "prompt": user_prompt,
                    "aspect_ratio": aspect,
                    "resolution": "4K",
                    "output_format": "jpg",
                    "image_input": photos[:14],
                }
            elif model_name == "nano_banana_pro":
                kie_model = "nano-banana-pro"
                input_data = {
                    "prompt": user_prompt,
                    "image_input": photos[:8],
                    "aspect_ratio": aspect,
                    "resolution": "2K",
                    "output_format": "png",
                }
            elif model_name == "seedream_text":
                kie_model = "seedream/4.5-text-to-image"
                input_data = {
                    "prompt": user_prompt,
                    "aspect_ratio": aspect,
                    "quality": "basic",
                    "nsfw_checker": False,
                }
            elif model_name == "seedream_edit":
                if not photos:
                    raise ValueError(
                        "Требуется хотя бы одно референсное фото для редактирования"
                    )
                kie_model = "seedream/4.5-edit"
                input_data = {
                    "prompt": user_prompt,
                    "image_urls": photos[:14],
                    "aspect_ratio": aspect,
                    "quality": "basic",
                    "nsfw_checker": False,
                }
            else:
                raise ValueError(f"Неизвестная модель фото: {model_name}")
            api_task_id = await self.api_client.create_kie_task(
                kie_model, input_data, api_key
            )
            self.db.update_task_status(task_id, "processing", api_task_id=api_task_id)
        except Exception as e:
            self.db.update_task_status(task_id, "failed", error_message=str(e))
            logging.error(f"Photo task {task_id} failed: {e}")
            await self._send_task_result(task_id)

    async def _process_ref_video_task(self, task_id: int):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT model, prompt FROM generation_tasks WHERE task_id = ?", (task_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return
        model, prompt_json = row
        try:
            data = json.loads(prompt_json)
            user_prompt = data["user_prompt"]
            aspect = data["aspect"]
            duration = data["duration"]
            refs = data["refs"]
            self.db.update_task_status(task_id, "processing")
            ref_model = data.get("ref_model", model)
            if ref_model == "grok":
                api_key = Config.KLING_API_KEY
                kie_model = "grok-imagine/image-to-video"
                input_data = {
                    "image_urls": refs[:7],
                    "prompt": user_prompt,
                    "aspect_ratio": aspect,
                    "mode": data.get("grok_mode", "normal"),
                    "duration": duration,
                    "resolution": data.get("grok_resolution", "720p"),
                    "nsfw_checker": False,
                }
            elif ref_model == "kling3":
                api_key = Config.KLING_API_KEY
                kie_model = "kling-3.0/video"
                kling_mode = data.get("kling_mode", "std")
                kling_sound = data.get("kling_sound", True)
                image_urls = refs[:2] if len(refs) >= 2 else (refs[:1] if refs else [])
                input_data = {
                    "prompt": user_prompt,
                    "image_urls": image_urls,
                    "sound": kling_sound,
                    "duration": str(duration),
                    "aspect_ratio": aspect,
                    "mode": kling_mode,
                    "multi_shots": False,
                }
            elif ref_model == "seedance2":
                api_key = Config.KLING_API_KEY
                kie_model = "bytedance/seedance-2"
                input_data = {
                    "prompt": user_prompt,
                    "reference_image_urls": refs[:9],
                    "aspect_ratio": aspect,
                    "duration": duration,
                    "resolution": data.get("seedance_resolution", "720p"),
                    "generate_audio": data.get("seedance_audio", True),
                    "nsfw_checker": False,
                }
            else:
                raise ValueError("Unknown model")
            api_task_id = await self.api_client.create_kie_task(
                kie_model, input_data, api_key
            )
            self.db.update_task_status(task_id, "processing", api_task_id=api_task_id)
        except Exception as e:
            self.db.update_task_status(task_id, "failed", error_message=str(e))
            logging.error(f"Ref video task {task_id} failed: {e}")
            await self._send_task_result(task_id)

    async def tbank_webhook_handler(self, request):
        try:
            data = await request.json()
            logging.info(f"TBank notify: {data}")

            # Validate notification token if not test mode
            if not Config.TBANK_IS_TEST:
                received_token = data.get("Token")
                if not received_token:
                    raise ValueError("No Token in notification")

                calculated_token = generate_token(data, Config.TBANK_SECRET_KEY)

                if data.get("TerminalKey", "").endswith("DEMO"):
                    logging.debug(
                        f"DEMO TBank token mismatch ignored for {data.get('OrderId')}"
                    )
                elif received_token != calculated_token:
                    logging.error(
                        f"TBank webhook token invalid. Expected: {calculated_token}, Got: {received_token}"
                    )
                    raise ValueError("Invalid webhook token")
            else:
                logging.info("TBank token validation skipped (test mode)")

            order_id = data["OrderId"]
            payment = self.db.get_payment_by_order_id(order_id)
            if not payment:
                logging.error(f"Payment not found: {order_id}")
                raise ValueError("Payment not found")

            payment_id = payment["id"]
            status = data.get("Status", "").upper()
            self.db.update_payment_status(payment_id, status)

            if status == "CONFIRMED" and payment.get("status") != "CONFIRMED":
                amount_rub = payment["amount_rub"]
                bananas = Config.PACKAGES.get(amount_rub, 0)
                user_id = payment["user_id"]
                if self.db.update_balance(
                    user_id, bananas, f"TBank payment {order_id} ({amount_rub}₽)"
                ):
                    logging.info(f"Balance updated +{bananas} for user {user_id}")
                    # Notify user
                    await self.bot.api.messages.send(
                        user_id=user_id,
                        message=f"✅ Пополнение прошло!\n+{bananas} 🍌 (за {amount_rub}₽)\nНовый баланс: {self.db.get_balance(user_id)} 🍌",
                        random_id=0,
                        keyboard=Keyboards.main_menu(),
                    )
                else:
                    logging.error(f"Balance update failed for {user_id}")

            return web.json_response({"Success": True})
        except Exception as e:
            logging.error(f"TBank notify error: {e}")
            return web.json_response({"Success": False, "Error": str(e)})

    async def pay_success_handler(self, request):
        order = request.query.get("order", "unknown")
        return web.Response(
            text=f"""
<!DOCTYPE html>
<html><body>
<h1>✅ Оплата успешна!</h1>
<p>Заказ {order}</p>
<p>Баланс обновлён автоматически. Вернитесь в бота.</p>
<a href="https://vk.com/im?sel={Config.VK_GROUP_ID}">← В бот</a>
</body></html>
        """,
            content_type="text/html",
        )

    async def pay_fail_handler(self, request):
        order = request.query.get("order", "unknown")
        return web.Response(
            text=f"""
<!DOCTYPE html>
<html><body>
<h1>❌ Оплата не удалась</h1>
<p>Заказ {order}</p>
<p>Попробуйте снова в боте.</p>
<a href="https://vk.com/im?sel={Config.VK_GROUP_ID}">← В бот</a>
</body></html>
        """,
            content_type="text/html",
        )

    async def webhook_handler(self, request):
        try:
            data = await request.json()
            logging.info(
                f"Webhook data: taskId={data.get('data', {}).get('taskId')}, state={data.get('data', {}).get('state')}"
            )
            task_data = data.get("data", {})
            kie_task_id = task_data.get("taskId")
            state = task_data.get("state")
            if not kie_task_id:
                return web.json_response({"status": "no taskId"}, status=400)
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT task_id, user_id FROM generation_tasks WHERE api_task_id = ?",
                (kie_task_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                logging.warning(f"Webhook task not found: {kie_task_id}")
                return web.json_response({"status": "task not found"}, status=404)
            local_task_id, user_id = row
            logging.info(
                f"Webhook processing task {local_task_id} (KIE {kie_task_id}), state {state}"
            )
            if state == "success":
                result_json_str = task_data.get("resultJson", "{}")
                result_json = json.loads(result_json_str)
                result_url = (
                    result_json.get("resultUrls", [None])[0]
                    or result_json.get("videoUrl")
                    or result_json.get("imageUrl")
                )
                logging.info(f"Task {local_task_id} success, URL: {result_url}")
                cursor.execute(
                    "UPDATE generation_tasks SET status = 'completed', result_url = ?, completed_at = CURRENT_TIMESTAMP WHERE task_id = ?",
                    (result_url, local_task_id),
                )
                conn.commit()
                await self._send_task_result(local_task_id)
            elif state == "fail":
                fail_msg = task_data.get("failMsg", "Unknown error")
                logging.error(f"Task {local_task_id} failed: {fail_msg}")
                cursor.execute(
                    "UPDATE generation_tasks SET status = 'failed', error_message = ? WHERE task_id = ?",
                    (fail_msg, local_task_id),
                )
                conn.commit()
                await self._send_task_result(local_task_id)
            else:
                logging.info(f"Task {local_task_id} state {state}, ignoring")
                conn.commit()

            conn.close()
            return web.json_response({"status": "ok"})
        except Exception as e:
            logging.error(f"Webhook handler error: {e}")
            return web.json_response({"status": "error", "msg": str(e)}, status=500)

    async def run_webhook_server(self):
        confirmation_response = await self.bot.api.request(
            "groups.getCallbackConfirmationCode", {"group_id": Config.VK_GROUP_ID}
        )
        self.confirmation_code = confirmation_response["response"]
        self.secret_key = "qejrxidddnfmnvqosmhuapeidnfeygwr"  # from existing VK server
        print(f"✅ Confirmation: {self.confirmation_code}")
        print(f"🔑 Secret: {self.secret_key}")
        print(f"VK Server URL: {Config.WEBHOOK_URL_VK}")
        print("Proxy /vk → localhost:8443/vk (nginx/Cloudflare)")
        app = web.Application()
        app.router.add_post("/vk", self.vk_handler)
        app.router.add_post("/webhook", self.webhook_handler)
        app.router.add_post("/webhook/tbank", self.tbank_webhook_handler)
        app.router.add_get("/pay_success", self.pay_success_handler)
        app.router.add_get("/pay_fail", self.pay_fail_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", 8443)
        await site.start()
        logging.info("Servers on 0.0.0.0:8443 (/vk VK events, /webhook AI)")
        await asyncio.Event().wait()

    async def run(self):
        print("🍌 Banana Boom Bot запущен на webhook!")
        await self.run_webhook_server()


if __name__ == "__main__":
    bot = BananaBoomBot()
    asyncio.run(bot.run())
