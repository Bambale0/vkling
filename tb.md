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

        # SHA-256
        return hashlib.sha256(values_str.encode("utf-8")).hexdigest()

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
        Инициировать платеж

production

test
POST
https://rest-api-test.tinkoff.ru/v2/Init



Описание
Метод инициирует платеж.

Запрос
Request body schema application/json

Required

TerminalKey

String

Requirements: <= 20 characters

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

Amount

Number

Requirements: <= 10 characters

Сумма в копейках. Например, 3 руб. 12коп. — это число 312.
Параметр должен быть равен сумме всех параметров Amount, переданных в объекте Items.
Минимальная сумма операции с помощью СБП составляет 10 руб.
Required

OrderId

String

Requirements: <= 36 characters

Идентификатор заказа в системе мерчанта. Должен быть уникальным для каждой операции.

Required

Token

String

Подпись запроса. Как сформировать.

Description

String

Requirements: <= 140 characters

Описание заказа. Значение параметра будет отображено на платежной форме.

Параметр обязательный при привязке и одновременной оплате через СБП. При оплате через СБП текст из этого параметра отобразится в мобильном банке клиента.

CustomerKey

String

Requirements: <= 36 characters

Идентификатор покупателя в системе мерчанта. Нужен для сохранения карт на платежной форме — платежи в один клик.

Параметр обязательный, если передан параметр Recurrent=Y и автоплатеж проводится по карте.

Если передан, в уведомлении будут указаны CustomerKey и его CardId. Подробнее — в методе Получить список карт клиента.

Recurrent

String

Requirements: <= 1 characters, [Y]

Признак родительского CC-платежа. Обязателен для проведения операции с сохранением реквизитов карты покупателя.

Если передается и установлен в Y, при платеже будут сохранены реквизиты карты покупателя. В этом случае после оплаты в уведомлении на AUTHORIZED будет передан параметр RebillId для использования в методе Провести платеж по сохраненным реквизитам. Для привязки и одновременной оплаты по CБП передавайте Y.

PayType

String

Requirements: [O, T]

Определяет тип проведения платежа:

O — одностадийная оплата;
T — двухстадийная оплата.
Если параметр передан, используется его значение, если нет — значение из настроек терминала.

Language

String

Requirements: <= 2 characters

Default: ru

Язык платежной формы:

ru — русский;
en — английский.
Если параметр не передан, форма откроется на русском языке.

NotificationURL

String<uri>

URL на веб-сайте мерчанта, куда будет отправлен POST-запрос о статусе выполнения вызываемых методов — настраивается в личном кабинете.

Если параметр передан, используется его значение, если нет — значение из настроек терминала.

Подробнее

SuccessURL

String<uri>

URL на веб-сайте мерчанта, куда будет переведен клиент в случае успешной оплаты — настраивается в личном кабинете.

Если параметр передан, используется его значение, если нет — значение из настроек терминала.

FailURL

String<uri>

URL на веб-сайте мерчанта, куда будет переведен клиент в случае неуспешной оплаты — настраивается в личном кабинете.

Если параметр передан, используется его значение, если нет — значение из настроек терминала.

RedirectDueDate

<date-time>

Cрок жизни ссылки или динамического QR-кода СБП, если выбран этот способ оплаты.

Если дата в параметре меньше текущей, оплата по ссылке и QR будет недоступна.

Минимальное значение — 1 минута от текущей даты.
Максимальное значение — 90 дней от текущей даты.
Формат даты — YYYY-MM-DDTHH24:MI:SS+GMT.
Пример даты — 2016-08-31T12:28:00+03:00.

Если параметр не был передан, проверяется настроечный параметр терминала REDIRECT_TIMEOUT, который содержит значение срока жизни ссылки в часах. Если его значение:

больше нуля — оно будет установлено в качестве срока жизни ссылки или динамического QR-кода;
меньше нуля — устанавливается значение по умолчанию: 1440 мин. (1 сутки).
DATA

Object

JSON-объект с дополнительными параметрами по операции и настройками в формате ключ:значение.

Максимальная длина ключа — 20 знаков, значения — 100 знаков.

Максимальное количество пар ключ:значение — не больше 20.

Если ключи или значения содержат в себе специальные символы, получившееся значение должно быть закодировано функцией urlencode.

Receipt

Object

JSON-объект с данными чека. Параметр обязательный, если подключена онлайн-касса.

Shops

Array of objects ()

JSON-объект с данными маркетплейса. Параметр обязательный для маркетплейсов.

Ответ
200

OK

Response schema application/json

Required

TerminalKey

String

Requirements: <= 20 characters

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

Amount

Number

Requirements: <= 20 characters

Сумма в копейках.

Required

OrderId

String

Requirements: <= 36 characters

Идентификатор заказа в системе мерчанта. Должен быть уникальным для каждой операции.

Required

Success

Boolean

Успешность прохождения запроса — true/false.

Required

Status

String

Requirements: <= 20 characters

Статус транзакции.

Required

PaymentId

String

Requirements: <= 20 characters

Идентификатор платежа в системе Т‑Бизнес.

Required

ErrorCode

String

Requirements: <= 20 characters

Код ошибки.

PaymentURL

String<uri>

Requirements: <= 100 characters

Ссылка на платежную форму. Параметр возвращается только для мерчантов, которые используют платежную форму Т-Банка.

Message

String

Requirements: <= 255 characters

Краткое описание ошибки.

Details

String

Подробное описание ошибки.
Подтвердить платеж

production

test
POST
https://rest-api-test.tinkoff.ru/v2/FinishAuthorize



Описание
Для мерчантов c собственной платежной формой

Метод подтверждает платеж:

при одностадийной оплате — списывает деньги за покупку сразу после завершения оплаты;
при двухстадийной — блокирует деньги за покупку на карте покупателя и только потом списывает их.
Запрос
Request body schema application/json

Required

TerminalKey

String

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

PaymentId

String

Requirements: <= 20 characters

Идентификатор платежа в системе Т‑Бизнес.

Required

Token

String

Подпись запроса. Как сформировать.

IP

String

IP-адрес покупателя в формате IPv4 и IPv6. DS платежной системы требует передавать IPv6 в полном формате — 8 групп по 4 символа.

Параметр обязательный для 3DS второй версии.

SendEmail

Boolean

Отправка уведомлений об оплате на почту покупателя:

true — отправлять;
false — не отправлять.
Source

String

Requirements: [cards, beeline, mts, tele2, megafon, einvoicing, webmoney]

Источник платежа. Значение параметра зависит от параметра Route:

ACQ — cards или Cards;
MC — beeline, mts, tele2, megafon;
EINV — einvoicing;
WM — webmoney.
DATA

Object

JSON-объект, который содержит дополнительные параметры в виде ключ:значение. Эти параметры будут переданы на страницу оплаты, если она кастомизирована.

Максимальная длина для каждого передаваемого параметра:

ключ — 20 знаков;
значение — 100 знаков.
Максимальное количество пар ключ:значение — не больше 20.

Если ключи или значения содержат в себе специальные символы, получившееся значение должно быть закодировано функцией urlencode.

InfoEmail

String<email>

Адрес почты покупателя. Параметр обязательный, если передан SendEmail=true.

EncryptedPaymentData

String

Данные карты. Параметр обязательный только для ApplePay или GooglePay.

Required

CardData

String

Объект CardData собирается в виде списка ключ=значение (разделитель ;) и зашифровывается открытым ключом — X509 RSA 2048. Бинарное значение кодируется в Base64.

Открытый ключ генерируется в Т‑Бизнес и выдается при регистрации терминала. Ключ доступен в личном кабинете Интернет-эквайринга в разделе Магазины.

Обязательные параметры с типом данных number:

PAN — номер карты;
ExpDate — месяц и год срока действия карты в формате MMYY.
Необязательные параметры с типом данных string:

CardHolder — имя и фамилия держателя карты как на карте.
CVV — код защиты с обратной стороны карты. Параметр необязательный для платежей через Apple Pay с расшифровкой токена на своей стороне.
ECI — Electronic Commerce Indicator. Индикатор, который показывает степень защиты, применяемой при предоставлении клиентом своих данных ТСП.
CAVV — Cardholder Authentication Verification Value или Accountholder Authentication Value.
Пример значения элемента формы CardData:

PAN=4300000000000777;ExpDate=0519;CardHolder=IVAN PETROV;CVV=111

Как получить платежный токен для MirPay при интеграции с НСПК

Если мерчант интегрируется только с банком для проведения платежа по MirPay, метод не вызывается. Эквайер самостоятельно получает платежный токен и инициирует авторизацию вместо мерчанта.

При получении CAVV в CardData оплата будет проводиться как оплата токеном — иначе прохождение 3DS будет регулироваться стандартными настройками терминала или платежа.

Параметр не используется, если передается EncryptedPaymentData.

Amount

Number

Requirements: <= 10 characters

Сумма в копейках.

deviceChannel

String

Default: 02

Канал устройства. Поддерживаются следующие каналы:

01 — Application (APP);
02 — Browser (BRW).
Не следует передавать параметр deviceChannel=02 — он установлен по умолчанию и подставляется автоматически. Если указать deviceChannel=02 явно, запрос завершится ошибкой: ErrorCode=204, Message=Неверные параметры, Details=Неверный токен. Проверьте пару TerminalKey/SecretKey.

Route

String

Requirements: [ACQ, MC, EINV, WM]

Способ платежа. Обязательный для ApplePay или GooglePay.

Ответ
200

OK

Response schema application/json

oneOf
Without3DS
With3DS
With3DSv2APP
With3DSv2BRW
Required

TerminalKey

String

Requirements: <= 20 characters

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

Amount

Number

Requirements: <= 20 characters

Сумма в копейках.

Required

OrderId

String

Requirements: <= 36 characters

Идентификатор заказа в системе мерчанта. Должен быть уникальным для каждой операции.

Required

Success

Boolean

Успешность прохождения запроса — true/false.

Required

Status

String

Requirements: <= 20 characters

Статус транзакции. Возвращается один из четырех статусов платежа:

CONFIRMED — при одностадийной оплате;
AUTHORIZED — при двухстадийной оплате;
3DS_CHECKING — когда нужно пройти проверку 3D Secure. Если используется своя платежная форма и платеж завис в этом статусе, нужно обратиться к эмитенту для устранения ошибок оплаты;
REJECTED — при неуспешном прохождении платежа.
PaymentId

String

Requirements: <= 20 characters

Идентификатор платежа в системе Т‑Бизнес.

Required

ErrorCode

String

Requirements: <= 20 characters

Код ошибки.

Message

String

Requirements: <= 255 characters

Краткое описание ошибки.

Details

String

Подробное описание ошибки.

RebillId

String

Уникальный идентификатор сохраненных реквизитов карты покупателя.

CardId

String

Идентификатор карты в системе Т‑Бизнес. Передается только для cохраненной карты.
Получить статус платежа

production

test
POST
https://rest-api-test.tinkoff.ru/v2/GetState



Описание
Метод возвращает статус платежа.

Подробнее про способы получения данных о платеже

Запрос
Request body schema application/json

Required

TerminalKey

String

Requirements: <= 20 characters

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

PaymentId

String

Requirements: <= 20 characters

Идентификатор платежа в системе Т‑Бизнес.

Required

Token

String

Подпись запроса. Как сформировать.

IP

String

IP-адрес покупателя.

Ответ
200

OK

Response schema application/json

Required

TerminalKey

String

Requirements: <= 20 characters

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

Amount

Number

Requirements: <= 20 characters

Сумма в копейках.

Required

OrderId

String

Requirements: <= 36 characters

Идентификатор заказа в системе мерчанта. Должен быть уникальным для каждой операции.

Required

Success

Boolean

Успешность прохождения запроса — true/false.

Required

Status

String

Requirements: <= 20 characters

Статус платежа.

Required

PaymentId

String

Requirements: <= 20 characters

Идентификатор платежа в системе Т‑Бизнес.

Required

ErrorCode

String

Requirements: <= 20 characters

Код ошибки.

Message

String

Краткое описание ошибки.

Details

String

Подробное описание ошибки.

Params

Array of objects ()

Информация по способу оплаты или деталям для платежей в рассрочку.
Отправить закрывающий чек в кассу

production
POST
https://securepay.tinkoff.ru/cashbox/SendClosingReceipt



Описание
Метод отправляет закрывающий чек в кассу.

Подробнее про работу с чеками

Запрос
Request body schema application/json

Required

TerminalKey

String

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

PaymentId

String

Идентификатор платежа в системе Т‑Бизнес.

Required

Receipt

Object

JSON-объект с данными чека.

Required

Token

String

Подпись запроса. Как сформировать.

Ответ
200

OK

Response schema application/json

Required

Success

Boolean

Успешность прохождения запроса — true/false.

Required

ErrorCode

String

Код ошибки.

Message

String

Requirements: <= 255 characters

Краткое описание ошибки.
Токен
Токен, или подпись запроса — это строка в запросе методов, в которой мерчант должен шифровать данные с помощью пароля.

В описании входных параметров для каждого метода указано, нужно подписывать запрос или нет. Токен формируется на основании тех полей, которые есть в запросе, поэтому для каждого запроса они уникальные и никогда не совпадают.

Сформировать токен

Пример запроса для метода Инициировать платеж
Чтобы зашифровать данные запроса:

Соберите массив передаваемых параметров в виде пар ключ:значение. В массив нужно добавить только параметры корневого объекта — вложенные объекты и массивы не участвуют в формировании токена.

В примере в массив включены параметры TerminalKey, Amount, OrderId, Description и исключены объекты Receipt и DATA:

[{"TerminalKey": "MerchantTerminalKey"},{"Amount": "19200"},{"OrderId": "00000"},{"Description": "Подарочная карта на 1000 рублей"}]


Добавьте в массив пару {"Password": "Значение пароля"}. Пароль можно найти в личном кабинете интернет-эквайринга.

[{"TerminalKey": "MerchantTerminalKey"},{"Amount": "19200"},{"OrderId": "00000"},{"Description": "Подарочная карта на 1000 рублей"},{"Password": "11111111111111"}]


Отсортируйте массив по алфавиту по ключу.

[{"Amount": "19200"},{"Description": "Подарочная карта на 1000 рублей"},{"OrderId": "00000"},{"Password": "11111111111111"},{"TerminalKey": "MerchantTerminalKey"}]


Конкатенируйте только значения пар в одну строку.

"19200Подарочная карта на 1000 рублей0000011111111111111MerchantTerminalKey"

Примените к строке хеш-функцию SHA-256 (с поддержкой UTF-8).

"72dd466f8ace0a37a1f740ce5fb78101712bc0665d91a8108c7c8a0ccd426db2"

Добавьте получившийся результат в значение параметра Token в тело запроса и отправьте его.

{
"TerminalKey": "MerchantTerminalKey",
"Amount": 19200,
"OrderId": "21090",
"Description": "Подарочная карта на 1000 рублей",
"DATA": {
  "Phone": "+71234567890",
  "Email": "a@test.com"
},
"Receipt": {
  "Email": "a@test.ru",
  "Phone": "+79031234567",
  "Taxation": "osn",
  "Items": [
    {
      "Name": "Наименование товара 1",
      "Price": 10000,
      "Quantity": 1,
      "Amount": 10000,
      "Tax": "vat10",
      "Ean13": "303130323930303030630333435"
    },
    {
      "Name": "Наименование товара 2",
      "Price": 20000,
      "Quantity": 2,
      "Amount": 40000,
      "Tax": "vat20"
    },
    {
      "Name": "Наименование товара 3",
      "Price": 30000,
      "Quantity": 3,
      "Amount": 90000,
      "Tax": "vat10"
    }
  ]
},
"Token": "72dd466f8ace0a37a1f740ce5fb78101712bc0665d91a8108c7c8a0ccd426db2"
}
"""Модуль для работы с API Т-Банк (эквайринг)."""
import hashlib
import json
import logging
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class TBankAPI:
    """Класс для работы с API Т-Банк по документации https://developer.tbank.ru/eacq/api"""

    def __init__(self, terminal_key: str, secret_key: str, api_url: str):
        self.terminal_key = terminal_key
        self.secret_key = secret_key
        self.api_url = api_url.rstrip("/")

    def _generate_token(self, params: Dict) -> str:
        """
        Генерация токена подписи по документации Т-Банк:

        1. Берём только параметры корневого объекта (без вложенных объектов и массивов)
        2. Добавляем {"Password": secret_key}
        3. Сортируем по алфавиту по ключу
        4. Конкатенируем значения в одну строку
        5. SHA-256 хеш
        """
        # Берём только скалярные параметры корневого уровня (str, int, bool)
        # Исключаем: Token, Receipt, DATA, Shops и другие объекты/массивы
        token_params = {}
        for key, value in params.items():
            # Пропускаем Token и сложные объекты
            if key == "Token":
                continue
            if isinstance(value, (str, int, float, bool)):
                token_params[key] = str(value)

        # Добавляем Password
        token_params["Password"] = self.secret_key

        # Сортируем по алфавиту
        sorted_keys = sorted(token_params.keys())

        # Конкатенируем значения
        values_str = "".join(token_params[k] for k in sorted_keys)

        # SHA-256
        return hashlib.sha256(values_str.encode("utf-8")).hexdigest()

    def init_payment(
        self,
        amount: int,  # в копейках
        order_id: str,
        description: str,
        customer_key: str,
        success_url: str,
        fail_url: str,
        notification_url: str,
        pay_type: str = "O",  # O - одностадийная, T - двухстадийная
        receipt: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Инициализация платежа (метод Init).

        Параметры Receipt и DATA не участвуют в формировании токена!
        """
        # Параметры для токена (только корневые скаляры)
        token_base = {
            "TerminalKey": self.terminal_key,
            "Amount": amount,
            "OrderId": str(order_id),
            "Description": description[:140] if description else "",
            "CustomerKey": str(customer_key),
            "SuccessURL": success_url,
            "FailURL": fail_url,
            "NotificationURL": notification_url,
            "PayType": pay_type,
            "Language": "ru",
        }

        # Формируем токен
        token = self._generate_token(token_base)

        # Итоговый payload с токеном и доп. объектами
        payload = {**token_base, "Token": token}

        # Добавляем вложенные объекты (не участвуют в токене!)
        if receipt:
            payload["Receipt"] = receipt
        if data:
            payload["DATA"] = data

        logger.debug(f"Init request: {json.dumps(payload, ensure_ascii=False)}")

        try:
            response = requests.post(
                f"{self.api_url}/Init",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            response.raise_for_status()
            result = response.json()

            logger.info(
                f"Init response: {result.get('Success')}, PaymentId={result.get('PaymentId')}"
            )

            if result.get("Success"):
                return result
            else:
                logger.error(
                    f"Init failed: {result.get('ErrorCode')} - {result.get('Message')}"
                )
                return None

        except Exception as e:
            logger.exception(f"Init request failed: {e}")
            return None

    def get_state(self, payment_id: str) -> Optional[Dict]:
        """Проверка статуса платежа (метод GetState)."""
        # Только скалярные параметры
        token_base = {"TerminalKey": self.terminal_key, "PaymentId": str(payment_id)}

        token = self._generate_token(token_base)

        payload = {**token_base, "Token": token}

        try:
            response = requests.post(
                f"{self.api_url}/GetState",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception(f"GetState failed: {e}")
            return None

    def confirm(self, payment_id: str, amount: int = None) -> Optional[Dict]:
        """Подтверждение списания для двухстадийного платежа (метод Confirm)."""
        token_base = {"TerminalKey": self.terminal_key, "PaymentId": str(payment_id)}
        if amount is not None:
            token_base["Amount"] = amount

        token = self._generate_token(token_base)

        payload = {**token_base, "Token": token}

        try:
            response = requests.post(
                f"{self.api_url}/Confirm",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception(f"Confirm failed: {e}")
            return None

    def cancel(self, payment_id: str) -> Optional[Dict]:
        """Отмена платежа (метод Cancel)."""
        token_base = {"TerminalKey": self.terminal_key, "PaymentId": str(payment_id)}

        token = self._generate_token(token_base)

        payload = {**token_base, "Token": token}

        try:
            response = requests.post(
                f"{self.api_url}/Cancel",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.exception(f"Cancel failed: {e}")
            return None

    def build_receipt(
        self, email: str, phone: str, items: List[Dict], taxation: str = "osn"
    ) -> Dict:
        """
        Формирование чека для 54-ФЗ.

        items: [{"Name": "...", "Price": 10000, "Quantity": 1.0, "Amount": 10000, "Tax": "none"}]
        """
        return {"Email": email, "Phone": phone, "Taxation": taxation, "Items": items}
Подтвердить списание

production

test
POST
https://securepay.tinkoff.ru/v2/Confirm



Описание
Метод подтверждает списание денег с карты покупателя.

Используется при двухстадийном платеже.

Применим только к платежам в статусе AUTHORIZED. Сумма списания может быть меньше или равна сумме авторизации.

Подробнее про реализацию двухстадийного платежа

Запрос
Request body schema application/json

Required

TerminalKey

String

Идентификатор терминала. Выдается мерчанту в Т‑Бизнес при заведении терминала.

Required

PaymentId

String

Requirements: <= 20 characters

Идентификатор платежа в системе Т‑Бизнес.

Required

Token

String

Подпись запроса. Как сформировать.

IP

String

IP-адрес покупателя.

Amount

Number

Сумма в копейках. Если не передан, используется Amount, который был передан в методе Инициировать платеж.

Receipt

Object

JSON-объект с данными чека. Обязателен, если подключена онлайн-касса.

Shops

Array of objects ()

JSON-объект с данными маркетплейса. Обязательный для маркетплейсов.

Route

String

Requirements: [TCB, BNPL]

Способ платежа.

Source

String

Requirements: [installment, BNPL]

Источник платежа.

Ответ
200

OK

Это полезный материал?


Да

Нет
Обратиться в поддержку
Сценарий использования

Прием платежей по двухстадийной схеме
Прием платежей по двухстадийной схеме на своей платежной форме
Пример запроса
Payload

cURL

Go

Java

NodeJs

PHP

Python

Content type

application/json



{

"TerminalKey":

"TBankTest",

"PaymentId":

"2304882",

"Token":

"c0ad1dfc4e94ed44715c5ed0e84f8ec439695b9ac219a7a19555a075a3c3ed24",

"IP":

"192.168.255.255",

"Amount":

19200,

"Receipt": { ... },
"Shops": [
{ ... }
],
"Route":

"BNPL",

"Source":

"BNPL"

}

Пример ответа
200
Content type

application/json



{

"TerminalKey":

"TBankTest",

"OrderId":

"21057",

"Success":

true,

"Status":

"CONFIRMED",

"PaymentId":

"2304882",

"ErrorCode":

"0",

"Message":

"OK",

"Details":

"None",

"Params": [
{
"Key":

"Route",

"Value":

"ACQ"

}
]
}
Уведомления об операциях
Уведомления об операциях — это уведомления мерчанту о статусе выполнения платежа. На основании этих уведомлений магазин должен предоставлять покупателю услугу или товар.

Чтобы настроить уведомления:

В личном кабинете интернет-эквайринга перейдите в раздел Магазины.
На вкладке Терминалы нажмите Настроить и выберите нужный вариант получения уведомлений — почта, HTTP(S) или оба варианта.
Вы можете получать уведомления не только о статусах платежа — также есть уведомления о привязке карты, фискализации и привязке счета по QR. Такие уведомления отправляются только на NotificationURL, заданный в настройках терминала.

Для HTTP(S)‑уведомлений передайте параметр NotificationURL в методе Инициировать платеж. Чтобы изменить значение этого параметра для метода Инициировать привязку карты к покупателю, обратитесь к персональному менеджеру или в поддержку банка.

Платеж (NotificationPayment)
После проведения платежа через вызов метода Инициировать платеж вам будет отправлена информация о статусе платежа.

На электронную почту
Т‑Бизнес будет присылать письма с уведомлениями об успешных платежах.

По HTTP(S)
При вызове методов:

Подтвердить списание и Отменить платеж — уведомление с информацией об операции отправляется через POST‑запрос на адрес NotificationURL.

Подтвердить платеж:

При двухстадийной оплате — уведомление с информацией об операции отправляется через POST‑запрос на адрес NotificationURL.

При одностадийной оплате — уведомление отправляется на ваш сайт на адрес NotificationURL и ждет ответа в течение 10 секунд. Сервис одновременно отправляет две нотификации — AUTHORIZED и CONFIRMED.

Для метода Провести платеж по сохраненным реквизитам логика такая же.

Привязать карту — уведомление отправляется на ваш сайт на адрес NotificationURL и ждет ответа в течение 10 секунд.

Если в NotificationURL используются порты, можно использовать порт 443 (HTTPS).


Список внешних сетей, которые использует Т-Банк
Дополнительные параметры
Чтобы включить дополнительные параметры DATA, обратитесь к своему персональному менеджеру.
Избегайте символов ', ", &, <, >, подлежащих экранированию в нотификациях.
Если значение параметра — null, оно не будет учитываться в формировании нотификации.
В уведомлениях можно получать дополнительные параметры. Для этого передайте объект DATA с нужными параметрами. В ответе вернется параметр Data — учитывайте регистр.

Пример набора параметров:

Параметр	Значение
description	Описание
name	ФИО
order_number	Идентификатор заказа
paymentId	Идентификатор платежа
source*	Способ оплаты
terminalKey	Идентификатор терминала
* При использовании платежной формы банка параметр source возвращается автоматически.

Чтобы получать POST‑запросы со статусами платежа, укажите URL в настройках терминала или передайте параметр NotificationURL в запросе метода Инициировать платеж. Если параметр передан, используется его значение, если нет — значение из настроек терминала.


Статусы платежа
Ответ на HTTP(s)-уведомление
При успешной обработке уведомления вам нужно вернуть ответ HTTP CODE = 200 с телом сообщения OK — без тегов, заглавными английскими буквами.

Если ответ OK не получен, уведомление считается неуспешным. Сервис будет повторно отправлять его раз в час в течение 24 часов, а затем раз в сутки в течение месяца. Если за это время оно так и не будет доставлено, уведомление будет перемещено в архив.

Уведомления хранятся в архиве 90 дней. В течение этого времени вы можете запросить их повторную отправку.


Параметры в теле уведомления о платеже

Пример уведомления о платеже
Привязка (NotificationAddCard)
Вам будет отправлена информация о статусе привязки после привязки карты через метод:

Иницировать привязку карты к покупателю, если используете банковскую форму привязки;
Привязать карту, если используете свою форму привязки.
Подробнее об отправке уведомлений.


Параметры в теле уведомления о привязке карты

Пример уведомления о привязке карты
Фискализация (NotificationFiscalization)
Если вы работаете по схеме интеграции «Маркетплейс», такой тип уведомлений не отправляется.

При подключенной онлайн-кассе по результату фискализации вам придет уведомление с фискальными данными. Чтобы включить такие уведомления, обратитесь в поддержку банка.


Параметры в теле уведомления о фискализации

Пример уведомления о фискализации
Статус привязки счета по QR (NotificationQr)
Такие уведомления будут приходить только по статусам ACTIVE и INACTIVE.

После успешной привязки счета по QR вам будет отправлена информация о статусе привязки счета и подпись запроса.


Параметры в теле уведомления о статусе привязки счета по QR

Пример уведомления о статусе привязки счета по QR
Проверить токен уведомлений
При получении уведомления и перед его обработкой проверьте токен:

Соберите массив всех переданных в нотификации параметров в виде пар ключ:значение — кроме параметра Token и вложенных объектов (Data, Receipt):

[{"TerminalKey": "1234567890DEMO"},{"OrderId": "000000"},{"Success": "true"},{"Status": "AUTHORIZED"},{"PaymentId": "0000000"},{"ErrorCode": "0"},{"Amount": "1111"},{"CardId": "000000"},{"Pan": "200000******0000"},{"ExpDate": "1111"},{"RebillId": "000000"}]


Добавьте в массив пару {"Password": "Значение пароля"}. Пароль можно найти в личном кабинете интернет-эквайринга.

[{"TerminalKey": "1234567890DEMO"},{"OrderId": "000000"},{"Success": "true"},{"Status": "AUTHORIZED"},{"PaymentId": "0000000"},{"ErrorCode": "0"},{"Amount": "1111"},{"CardId": "000000"},{"Pan": "200000******0000"},{"ExpDate": "1111"},{"RebillId": "000000"},{"Password": "11111111111"}]


Отсортируйте массив по алфавиту по ключу:

[{"Amount": "1111"},{"CardId": "000000"},{"ErrorCode": "0"},{"ExpDate": "1111"},{"OrderId": "000000"},{"Pan": "200000******0000"},{"Password": "11111111111"},{"PaymentId": "0000000"},{"RebillId": "000000"},{"Status": "AUTHORIZED"},{"Success": "true"},{"TerminalKey": "1234567890DEMO"}]


Конкатенируйте только значения пар в одну строку:

111100000001111000000200000******0000111111111110000000000000AUTHORIZEDtrue1234567890DEMO

Примените к строке хеш-функцию SHA-256 (с поддержкой UTF-8):

1c0964277d0213349243065a0d5b838b8e90d2d25f740d0f2767836e710e80c8


Пример генерации токена

Пример сравнения токенов
Для проверки токена уведомления о привязке карты используйте следующие параметры:

TerminalKey,
CustomerKey,
RequestKey,
Success,
Status,
PaymentId,
ErrorCode,
CardId,
Pan,
ExpDate,
NotificationType,
RebillId — параметр передается, если был присвоен во время привязки.
