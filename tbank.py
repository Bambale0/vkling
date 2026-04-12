"""Модуль для работы с API Т-Банк (эквайринг)."""

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Union

import requests

logger = logging.getLogger(__name__)


class TBankAPI:
    """Класс для работы с API Т-Банк по документации https://developer.tbank.ru/eacq"""

    def __init__(
        self, terminal_key: str, secret_key: str, api_url: str, timeout: int = 15
    ):
        """
        Инициализация клиента.

        :param terminal_key: Идентификатор терминала (выдаётся в Т‑Бизнес)
        :param secret_key: Секретный ключ (пароль) для подписи запросов
        :param api_url: Базовый URL API (например, https://rest-api-test.tinkoff.ru/v2)
        :param timeout: Таймаут запросов в секундах (по умолчанию 15)
        """
        self.terminal_key = terminal_key
        self.secret_key = secret_key
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

    def _generate_token(self, params: Dict[str, Any]) -> str:
        """
        Генерация токена подписи по документации Т-Банк:

        1. Принимаются только скалярные параметры (строки, числа, булевы)
        2. Добавляется {"Password": secret_key}
        3. Сортировка по алфавиту по ключу
        4. Конкатенация значений (все приведены к строке)
        5. SHA-256 хеш (UTF-8)

        :param params: Словарь параметров (без Token и вложенных объектов)
        :return: Токен (hex-строка)
        """
        # Копируем только скалярные значения, исключая Token
        token_params = {}
        for key, value in params.items():
            if key == "Token":
                continue
            if isinstance(value, (str, int, float, bool)):
                # Булевы значения приводим к "true"/"false" (нижний регистр)
                if isinstance(value, bool):
                    token_params[key] = "true" if value else "false"
                else:
                    token_params[key] = str(value)
            # Остальные типы (dict, list) игнорируем – они не участвуют в токене

        # Добавляем пароль
        token_params["Password"] = self.secret_key

        # Сортируем ключи по алфавиту
        sorted_keys = sorted(token_params.keys())

        # Конкатенируем значения
        values_str = "".join(token_params[k] for k in sorted_keys)

        logger.debug(f"Token params sorted keys: {sorted_keys}")
        logger.debug(f"Token concat string: {repr(values_str)}")

        # SHA-256
        token = hashlib.sha256(values_str.encode("utf-8")).hexdigest()
        logger.debug(f"Generated token: {token}")
        return token

    def _post(self, endpoint: str, payload: Dict) -> Optional[Dict]:
        """
        Внутренний метод для POST-запроса с обработкой ошибок и логированием.
        """
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        logger.info(
            f"Request to {url}: {json.dumps(payload, ensure_ascii=False, default=str)}"
        )
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Response: {json.dumps(result, ensure_ascii=False)}")
            return result
        except requests.exceptions.RequestException as e:
            logger.exception(f"HTTP request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.exception(f"Invalid JSON response: {e}")
            return None

    # -------------------------------------------------------------------------
    # Методы API
    # -------------------------------------------------------------------------

    def init_payment(
        self,
        amount: int,
        order_id: str,
        description: str,
        customer_key: Optional[str] = None,
        success_url: Optional[str] = None,
        fail_url: Optional[str] = None,
        notification_url: Optional[str] = None,
        pay_type: str = "O",
        recurrent: Optional[str] = None,  # "Y" или None
        redirect_due_date: Optional[str] = None,  # строка с датой и таймзоной
        language: str = "ru",
        receipt: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Инициализация платежа (метод Init).

        :param amount: Сумма в копейках
        :param order_id: Идентификатор заказа (до 36 символов)
        :param description: Описание заказа (до 140 символов)
        :param customer_key: Идентификатор покупателя (для сохранения карт)
        :param success_url: URL при успешной оплате
        :param fail_url: URL при неуспешной оплате
        :param notification_url: URL для уведомлений
        :param pay_type: Тип платежа: "O" (одностадийный) или "T" (двухстадийный)
        :param recurrent: Признак родительского рекуррентного платежа ("Y")
        :param redirect_due_date: Срок жизни ссылки / QR-кода (ISO8601 с таймзоной)
        :param language: Язык платежной формы ("ru" / "en")
        :param receipt: Данные чека (объект)
        :param data: Дополнительные параметры (объект)
        :return: Ответ API или None при ошибке
        """
        # Формируем базовые параметры (только скаляры)
        params = {
            "TerminalKey": self.terminal_key,
            "Amount": amount,
            "OrderId": str(order_id)[:36],
            "Description": description[:140] if description else "",
            "Language": language,
            "PayType": pay_type,
        }

        # Добавляем опциональные параметры, если они переданы
        if customer_key is not None:
            params["CustomerKey"] = str(customer_key)[:36]
        if success_url is not None:
            params["SuccessURL"] = success_url
        if fail_url is not None:
            params["FailURL"] = fail_url
        if notification_url is not None:
            params["NotificationURL"] = notification_url
        if recurrent is not None:
            params["Recurrent"] = recurrent
        if redirect_due_date is not None:
            params["RedirectDueDate"] = redirect_due_date

        # Генерируем токен
        token = self._generate_token(params)

        # Формируем полный payload
        payload = {**params, "Token": token}
        if receipt:
            payload["Receipt"] = receipt
            # Детальное логирование чека для отладки
            total_amount = sum(
                item.get("Amount", 0) for item in receipt.get("Items", [])
            )
            logger.info(f"Receipt total: {total_amount}, Payment amount: {amount}")
        if data:
            payload["DATA"] = data

        return self._post("Init", payload)

    def finish_authorize(
        self,
        payment_id: str,
        ip: Optional[str] = None,
        send_email: Optional[bool] = None,
        info_email: Optional[str] = None,
        encrypted_payment_data: Optional[str] = None,
        card_data: Optional[str] = None,
        route: Optional[str] = None,  # "ACQ", "MC", "EINV", "WM"
        data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Завершение авторизации платежа (метод FinishAuthorize).
        Используется для подтверждения после 3DS или при оплате картой с передачей данных карты.

        :param payment_id: Идентификатор платежа в системе Т‑Банк
        :param ip: IP-адрес покупателя (обязателен для 3DS v2)
        :param send_email: Отправлять ли уведомление на почту
        :param info_email: Адрес почты (обязателен, если send_email=True)
        :param encrypted_payment_data: Зашифрованные данные для Apple Pay / Google Pay
        :param card_data: Данные карты (PAN;ExpDate;CardHolder;CVV), зашифрованные открытым ключом
        :param route: Способ платежа (например, "ACQ")
        :param data: Дополнительные параметры (объект)
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "PaymentId": str(payment_id),
        }
        if ip is not None:
            params["IP"] = ip
        if send_email is not None:
            params["SendEmail"] = send_email
        if info_email is not None:
            params["InfoEmail"] = info_email
        if encrypted_payment_data is not None:
            params["EncryptedPaymentData"] = encrypted_payment_data
        if card_data is not None:
            params["CardData"] = card_data
        if route is not None:
            params["Route"] = route

        token = self._generate_token(params)
        payload = {**params, "Token": token}
        if data:
            payload["DATA"] = data

        return self._post("FinishAuthorize", payload)

    def confirm(self, payment_id: str, amount: Optional[int] = None) -> Optional[Dict]:
        """
        Подтверждение списания для двухстадийного платежа (метод Confirm).

        :param payment_id: Идентификатор платежа
        :param amount: Сумма списания в копейках (если не указана, списывается полная сумма)
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "PaymentId": str(payment_id),
        }
        if amount is not None:
            params["Amount"] = amount

        token = self._generate_token(params)
        payload = {**params, "Token": token}
        return self._post("Confirm", payload)

    def cancel(self, payment_id: str) -> Optional[Dict]:
        """
        Отмена платежа (метод Cancel).

        :param payment_id: Идентификатор платежа
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "PaymentId": str(payment_id),
        }
        token = self._generate_token(params)
        payload = {**params, "Token": token}
        return self._post("Cancel", payload)

    def get_state(self, payment_id: str) -> Optional[Dict]:
        """
        Получение статуса платежа (метод GetState).

        :param payment_id: Идентификатор платежа
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "PaymentId": str(payment_id),
        }
        token = self._generate_token(params)
        payload = {**params, "Token": token}
        return self._post("GetState", payload)

    def get_card_list(self, customer_key: str) -> Optional[Dict]:
        """
        Получение списка сохранённых карт клиента (метод GetCardList).

        :param customer_key: Идентификатор покупателя
        :return: Ответ API со списком карт в поле Cards
        """
        params = {
            "TerminalKey": self.terminal_key,
            "CustomerKey": str(customer_key),
        }
        token = self._generate_token(params)
        payload = {**params, "Token": token}
        return self._post("GetCardList", payload)

    def remove_card(
        self, card_id: str, customer_key: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Удаление сохранённой карты (метод RemoveCard).

        :param card_id: Идентификатор карты в системе Т‑Банк
        :param customer_key: Идентификатор покупателя (требуется не всегда, но рекомендуется)
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "CardId": str(card_id),
        }
        if customer_key is not None:
            params["CustomerKey"] = str(customer_key)

        token = self._generate_token(params)
        payload = {**params, "Token": token}
        return self._post("RemoveCard", payload)

    def resend(self, payment_id: str) -> Optional[Dict]:
        """
        Повторная отправка уведомления на NotificationURL (метод Resend).

        :param payment_id: Идентификатор платежа
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "PaymentId": str(payment_id),
        }
        token = self._generate_token(params)
        payload = {**params, "Token": token}
        return self._post("Resend", payload)

    def send_closing_receipt(self, payment_id: str, receipt: Dict) -> Optional[Dict]:
        """
        Отправка закрывающего чека в кассу (метод SendClosingReceipt).

        :param payment_id: Идентификатор платежа
        :param receipt: Данные чека (объект)
        :return: Ответ API
        """
        params = {
            "TerminalKey": self.terminal_key,
            "PaymentId": str(payment_id),
        }
        token = self._generate_token(params)
        payload = {**params, "Token": token, "Receipt": receipt}
        return self._post("SendClosingReceipt", payload)

    # -------------------------------------------------------------------------
    # Вспомогательные методы для построения объектов
    # -------------------------------------------------------------------------

    @staticmethod
    def build_receipt(
        email: str, phone: str, items: List[Dict], taxation: str = "osn"
    ) -> Dict:
        """
        Формирование объекта чека для 54-ФЗ.

        :param email: Email покупателя
        :param phone: Телефон покупателя
        :param items: Список товаров. Каждый товар — словарь с полями:
                      Name (str), Price (int, в копейках), Quantity (float),
                      Amount (int, Price * Quantity), Tax (str, ставка НДС)
        :param taxation: Система налогообложения (по умолчанию "osn")
        :return: Словарь чека
        """
        return {"Email": email, "Phone": phone, "Taxation": taxation, "Items": items}
