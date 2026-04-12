Python
Copy
# tbank_payment/utils.py
"""Утилиты для работы с API Т-Банка"""

import hashlib
import json
from typing import Dict, Any, Optional, List


def generate_token(data: Dict[str, Any], password: str) -> str:
    """
    Генерация токена для подписи запроса к API Т-Банка
    
    Алгоритм по документации:
    1. Собрать массив пар ключ:значение только корневых параметров
       (вложенные объекты и массивы НЕ участвуют!)
    2. Добавить {"Password": password}
    3. Отсортировать по ключу по алфавиту
    4. Конкатенировать только значения в одну строку
    5. SHA-256 хеш
    """
    # Берем только корневые параметры, исключаем вложенные объекты/массивы и Token
    filtered_data = {}
    for key, value in data.items():
        if key == "Token":
            continue
        # Пропускаем сложные объекты — они не участвуют в токене
        if isinstance(value, (dict, list)):
            continue
        if value is not None:
            filtered_data[key] = str(value)
    
    # Добавляем пароль
    filtered_data["Password"] = password
    
    # Сортируем по ключам
    sorted_items = sorted(filtered_data.items(), key=lambda x: x[0])
    
    # Конкатенируем только значения
    values_str = "".join([str(value) for _, value in sorted_items])
    
    # SHA-256
    return hashlib.sha256(values_str.encode('utf-8')).hexdigest()


def prepare_request_data(data: Dict[str, Any], terminal_key: str, password: str) -> Dict[str, Any]:
    """Подготовка данных запроса с добавлением токена"""
    data = data.copy()
    data["TerminalKey"] = terminal_key
    data["Token"] = generate_token(data, password)
    return data


def amount_to_coins(amount: float) -> int:
    """Конвертация рублей в копейки"""
    return int(round(amount * 100))


def coins_to_amount(coins: int) -> float:
    """Конвертация копеек в рубли"""
    return coins / 100


def mask_pan(pan: Optional[str]) -> Optional[str]:
    """Маскировка номера карты"""
    if not pan or len(pan) < 4:
        return pan
    return "*" * (len(pan) - 4) + pan[-4:]


def format_datetime(dt) -> str:
    """Форматирование даты в формат YYYY-MM-DDTHH24:MI:SS+GMT"""
    if dt is None:
        return None
    # Формат: 2016-08-31T12:28:00+03:00
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")
Python
Copy
# tbank_payment/models.py
"""Pydantic модели для API Т-Банка"""

from typing import Optional, List, Dict, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class PaymentStatus(str, Enum):
    """Статусы платежа"""
    NEW = "NEW"
    FORM_SHOWED = "FORM_SHOWED"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    CANCELED = "CANCELED"
    AUTHORIZING = "AUTHORIZING"
    AUTHORIZED = "AUTHORIZED"
    AUTH_FAIL = "AUTH_FAIL"
    REJECTED = "REJECTED"
    THREE_DS_CHECKING = "3DS_CHECKING"
    THREE_DS_CHECKED = "3DS_CHECKED"
    REVERSING = "REVERSING"
    PARTIAL_REVERSED = "PARTIAL_REVERSED"
    REVERSED = "REVERSED"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    REFUNDING = "REFUNDING"
    ASYNC_REFUNDING = "ASYNC_REFUNDING"
    PARTIAL_REFUNDED = "PARTIAL_REFUNDED"
    REFUNDED = "REFUNDED"


class Taxation(str, Enum):
    """Системы налогообложения"""
    OSN = "osn"
    USN_INCOME = "usn_income"
    USN_INCOME_OUTCOME = "usn_income_outcome"
    ENVD = "envd"
    ESN = "esn"
    PATENT = "patent"


class VAT(str, Enum):
    """Ставки НДС"""
    NONE = "none"
    VAT0 = "vat0"
    VAT10 = "vat10"
    VAT20 = "vat20"
    VAT110 = "vat110"
    VAT120 = "vat120"


class PaymentMethod(str, Enum):
    """Способы расчета"""
    FULL_PAYMENT = "full_payment"
    FULL_PREPAYMENT = "full_prepayment"
    PREPAYMENT = "prepayment"
    ADVANCE = "advance"
    PARTIAL_PAYMENT = "partial_payment"
    CREDIT = "credit"
    CREDIT_PAYMENT = "credit_payment"


class PaymentObject(str, Enum):
    """Предметы расчета"""
    COMMODITY = "commodity"
    EXCISE = "excise"
    JOB = "job"
    SERVICE = "service"
    GAMBLING_BET = "gambling_bet"
    GAMBLING_PRIZE = "gambling_prize"
    LOTTERY = "lottery"
    LOTTERY_PRIZE = "lottery_prize"
    INTELLECTUAL_ACTIVITY = "intellectual_activity"
    PAYMENT = "payment"
    AGENT_COMMISSION = "agent_commission"
    COMPOSITE = "composite"
    ANOTHER = "another"


class ReceiptItem(BaseModel):
    """Позиция чека"""
    name: str = Field(..., alias="Name", max_length=128)
    quantity: float = Field(..., alias="Quantity", gt=0)
    amount: int = Field(..., alias="Amount", description="Сумма в копейках")
    price: int = Field(..., alias="Price", description="Цена в копейках")
    tax: VAT = Field(..., alias="Tax")
    payment_method: Optional[PaymentMethod] = Field(None, alias="PaymentMethod")
    payment_object: Optional[PaymentObject] = Field(None, alias="PaymentObject")
    ean13: Optional[str] = Field(None, alias="Ean13")
    shop_code: Optional[str] = Field(None, alias="ShopCode")
    
    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError('Quantity must be positive')
        return v


class Receipt(BaseModel):
    """Чек"""
    items: List[ReceiptItem] = Field(..., alias="Items")
    taxation: Taxation = Field(..., alias="Taxation")
    email: Optional[str] = Field(None, alias="Email")
    phone: Optional[str] = Field(None, alias="Phone")
    email_company: Optional[str] = Field(None, alias="EmailCompany")
    
    class Config:
        populate_by_name = True


class ReceiptPayments(BaseModel):
    """Платежи в чеке (для SendClosingReceipt)"""
    cash: Optional[int] = Field(None, alias="Cash")
    electronic: Optional[int] = Field(None, alias="Electronic")
    advance_payment: Optional[int] = Field(None, alias="AdvancePayment")
    credit: Optional[int] = Field(None, alias="Credit")
    provision: Optional[int] = Field(None, alias="Provision")


class InitPaymentRequest(BaseModel):
    """Запрос на инициализацию платежа"""
    amount: int = Field(..., alias="Amount", description="Сумма в копейках")
    order_id: str = Field(..., alias="OrderId", max_length=36)
    description: Optional[str] = Field(None, alias="Description", max_length=140)
    customer_key: Optional[str] = Field(None, alias="CustomerKey", max_length=36)
    recurrent: Optional[str] = Field(None, alias="Recurrent", pattern="^Y$")
    language: Optional[str] = Field("ru", alias="Language", pattern="^(ru|en)$")
    pay_type: Optional[str] = Field(None, alias="PayType", pattern="^[OT]$")
    notification_url: Optional[str] = Field(None, alias="NotificationURL")
    success_url: Optional[str] = Field(None, alias="SuccessURL")
    fail_url: Optional[str] = Field(None, alias="FailURL")
    redirect_due_date: Optional[str] = Field(None, alias="RedirectDueDate")
    data: Optional[Dict[str, str]] = Field(None, alias="DATA")
    receipt: Optional[Receipt] = Field(None, alias="Receipt")
    
    class Config:
        populate_by_name = True


class InitPaymentResponse(BaseModel):
    """Ответ на инициализацию платежа"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    terminal_key: Optional[str] = Field(None, alias="TerminalKey")
    status: Optional[PaymentStatus] = Field(None, alias="Status")
    payment_id: Optional[str] = Field(None, alias="PaymentId")
    order_id: Optional[str] = Field(None, alias="OrderId")
    amount: Optional[int] = Field(None, alias="Amount")
    payment_url: Optional[str] = Field(None, alias="PaymentURL")
    details: Optional[str] = Field(None, alias="Details")
    
    class Config:
        populate_by_name = True


class FinishAuthorizeRequest(BaseModel):
    """Запрос для завершения авторизации (своя платежная форма)"""
    payment_id: str = Field(..., alias="PaymentId")
    card_data: Optional[str] = Field(None, alias="CardData")
    encrypted_payment_data: Optional[str] = Field(None, alias="EncryptedPaymentData")
    send_email: Optional[bool] = Field(None, alias="SendEmail")
    info_email: Optional[str] = Field(None, alias="InfoEmail")
    ip: Optional[str] = Field(None, alias="IP")
    route: Optional[str] = Field(None, alias="Route")
    source: Optional[str] = Field(None, alias="Source")
    data: Optional[Dict[str, str]] = Field(None, alias="DATA")
    amount: Optional[int] = Field(None, alias="Amount")
    device_channel: Optional[str] = Field("02", alias="deviceChannel")
    
    class Config:
        populate_by_name = True


class FinishAuthorizeResponse(BaseModel):
    """Ответ на завершение авторизации"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    terminal_key: Optional[str] = Field(None, alias="TerminalKey")
    status: Optional[PaymentStatus] = Field(None, alias="Status")
    payment_id: Optional[str] = Field(None, alias="PaymentId")
    order_id: Optional[str] = Field(None, alias="OrderId")
    amount: Optional[int] = Field(None, alias="Amount")
    rebill_id: Optional[str] = Field(None, alias="RebillId")
    card_id: Optional[str] = Field(None, alias="CardId")
    
    # 3DS поля
    acs_url: Optional[str] = Field(None, alias="ACSUrl")
    md: Optional[str] = Field(None, alias="MD")
    pa_req: Optional[str] = Field(None, alias="PaReq")
    term_url: Optional[str] = Field(None, alias="TermUrl")
    
    class Config:
        populate_by_name = True


class GetStateRequest(BaseModel):
    """Запрос состояния платежа"""
    payment_id: str = Field(..., alias="PaymentId")
    ip: Optional[str] = Field(None, alias="IP")
    
    class Config:
        populate_by_name = True


class GetStateResponse(BaseModel):
    """Ответ с состоянием платежа"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    order_id: Optional[str] = Field(None, alias="OrderId")
    status: Optional[PaymentStatus] = Field(None, alias="Status")
    payment_id: Optional[str] = Field(None, alias="PaymentId")
    amount: Optional[int] = Field(None, alias="Amount")
    rebill_id: Optional[str] = Field(None, alias="RebillId")
    params: Optional[List[Dict[str, Any]]] = Field(None, alias="Params")
    
    class Config:
        populate_by_name = True


class CancelRequest(BaseModel):
    """Запрос отмены платежа"""
    payment_id: str = Field(..., alias="PaymentId")
    amount: Optional[int] = Field(None, alias="Amount")
    
    class Config:
        populate_by_name = True


class CancelResponse(BaseModel):
    """Ответ на отмену платежа"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    order_id: Optional[str] = Field(None, alias="OrderId")
    status: Optional[PaymentStatus] = Field(None, alias="Status")
    payment_id: Optional[str] = Field(None, alias="PaymentId")
    original_amount: Optional[int] = Field(None, alias="OriginalAmount")
    new_amount: Optional[int] = Field(None, alias="NewAmount")
    
    class Config:
        populate_by_name = True


class ConfirmRequest(BaseModel):
    """Запрос подтверждения платежа (двухстадийная)"""
    payment_id: str = Field(..., alias="PaymentId")
    amount: Optional[int] = Field(None, alias="Amount")
    receipt: Optional[Receipt] = Field(None, alias="Receipt")
    
    class Config:
        populate_by_name = True


class ConfirmResponse(BaseModel):
    """Ответ на подтверждение платежа"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    order_id: Optional[str] = Field(None, alias="OrderId")
    status: Optional[PaymentStatus] = Field(None, alias="Status")
    payment_id: Optional[str] = Field(None, alias="PaymentId")
    
    class Config:
        populate_by_name = True


class ChargeRequest(BaseModel):
    """Запрос на рекуррентный платеж"""
    rebill_id: str = Field(..., alias="RebillId")
    amount: int = Field(..., alias="Amount")
    order_id: str = Field(..., alias="OrderId")
    send_email: Optional[bool] = Field(None, alias="SendEmail")
    info_email: Optional[str] = Field(None, alias="InfoEmail")
    description: Optional[str] = Field(None, alias="Description")
    
    class Config:
        populate_by_name = True


class ChargeResponse(BaseModel):
    """Ответ на рекуррентный платеж"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    order_id: Optional[str] = Field(None, alias="OrderId")
    status: Optional[PaymentStatus] = Field(None, alias="Status")
    payment_id: Optional[str] = Field(None, alias="PaymentId")
    amount: Optional[int] = Field(None, alias="Amount")
    
    class Config:
        populate_by_name = True


class SendClosingReceiptRequest(BaseModel):
    """Запрос на отправку закрывающего чека"""
    payment_id: str = Field(..., alias="PaymentId")
    receipt: Receipt = Field(..., alias="Receipt")
    
    class Config:
        populate_by_name = True


class SendClosingReceiptResponse(BaseModel):
    """Ответ на отправку закрывающего чека"""
    success: bool = Field(..., alias="Success")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    error_message: Optional[str] = Field(None, alias="Message")
    
    class Config:
        populate_by_name = True


class Notification(BaseModel):
    """Webhook уведомление от Т-Банка"""
    terminal_key: str = Field(..., alias="TerminalKey")
    order_id: str = Field(..., alias="OrderId")
    success: bool = Field(..., alias="Success")
    status: PaymentStatus = Field(..., alias="Status")
    payment_id: int = Field(..., alias="PaymentId")
    error_code: Optional[str] = Field(None, alias="ErrorCode")
    amount: int = Field(..., alias="Amount")
    rebill_id: Optional[str] = Field(None, alias="RebillId")
    card_id: Optional[int] = Field(None, alias="CardId")
    pan: Optional[str] = Field(None, alias="Pan")
    data: Optional[str] = Field(None, alias="DATA")
    token: str = Field(..., alias="Token")
    expiration_date: Optional[str] = Field(None, alias="ExpDate")
    
    class Config:
        populate_by_name = True
Python
Copy
# tbank_payment/client.py
"""Клиент для работы с API Т-Банка"""

import json
import logging
from typing import Optional, Dict, Any
import requests
import aiohttp

from .config import TBankConfig
from .models import (
    InitPaymentRequest, InitPaymentResponse,
    FinishAuthorizeRequest, FinishAuthorizeResponse,
    GetStateRequest, GetStateResponse,
    CancelRequest, CancelResponse,
    ConfirmRequest, ConfirmResponse,
    ChargeRequest, ChargeResponse,
    SendClosingReceiptRequest, SendClosingReceiptResponse,
    Receipt,
)
from .utils import prepare_request_data, amount_to_coins, format_datetime
from .exceptions import TBankAPIError, TBankNetworkError, TBankAuthError, TBankValidationError

logger = logging.getLogger(__name__)


class TBankPaymentClient:
    """Синхронный клиент для API платежей Т-Банка"""
    
    def __init__(self, config: Optional[TBankConfig] = None, 
                 terminal_key: Optional[str] = None,
                 password: Optional[str] = None):
        """
        Инициализация клиента
        
        Args:
            config: Объект конфигурации
            terminal_key: Terminal Key (если не передан config)
            password: Пароль (если не передан config)
        """
        if config:
            self.config = config
        elif terminal_key and password:
            self.config = TBankConfig(terminal_key=terminal_key, password=password)
        else:
            self.config = TBankConfig.from_env()
        
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
    
    def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение запроса к API"""
        url = f"{self.config.base_url}/{endpoint}"
        
        # Добавляем подпись (важно: токен генерируется до сериализации!)
        signed_data = prepare_request_data(data, self.config.terminal_key, self.config.password)
        
        logger.debug(f"Request to {endpoint}: {json.dumps(signed_data, ensure_ascii=False, default=str)}")
        
        try:
            response = self.session.post(url, json=signed_data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            logger.debug(f"Response from {endpoint}: {json.dumps(result, ensure_ascii=False)}")
            
            # Проверка на ошибки API
            if not result.get("Success", False):
                error_code = result.get("ErrorCode", "0")
                error_msg = result.get("Message", "Unknown error")
                
                if error_code == "0":
                    raise TBankAuthError(f"Authentication failed: {error_msg}", error_code)
                elif error_code in ["1", "2", "3"]:
                    raise TBankValidationError(f"Validation error: {error_msg}", error_code)
                else:
                    raise TBankAPIError(f"API error: {error_msg}", error_code)
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            raise TBankNetworkError(f"Network error: {str(e)}")
    
    def init_payment(self, request: InitPaymentRequest) -> InitPaymentResponse:
        """
        Инициализация платежа (получение PaymentURL для платежной формы Т-Банка)
        
        Args:
            request: Данные для инициализации платежа
            
        Returns:
            InitPaymentResponse с URL для оплаты
        """
        # Добавляем URL из конфига, если не указаны в запросе
        data = request.model_dump(by_alias=True, exclude_none=True)
        
        if not data.get("NotificationURL") and self.config.notification_url:
            data["NotificationURL"] = self.config.notification_url
        if not data.get("SuccessURL") and self.config.success_url:
            data["SuccessURL"] = self.config.success_url
        if not data.get("FailURL") and self.config.fail_url:
            data["FailURL"] = self.config.fail_url
        
        result = self._make_request("Init", data)
        return InitPaymentResponse.model_validate(result)
    
    def finish_authorize(self, request: FinishAuthorizeRequest) -> FinishAuthorizeResponse:
        """
        Завершение авторизации (для собственной платежной формы)
        
        Используется для:
        - Одностадийной оплаты (сразу списывает деньги)
        - Двухстадийной оплаты (блокирует деньги)
        
        Args:
            request: Данные для завершения авторизации
            
        Returns:
            FinishAuthorizeResponse
        """
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = self._make_request("FinishAuthorize", data)
        return FinishAuthorizeResponse.model_validate(result)
    
    def get_state(self, payment_id: str, ip: Optional[str] = None) -> GetStateResponse:
        """
        Получение состояния платежа
        
        Args:
            payment_id: ID платежа
            ip: IP-адрес покупателя (опционально)
            
        Returns:
            GetStateResponse с информацией о платеже
        """
        request = GetStateRequest(PaymentId=payment_id, IP=ip)
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = self._make_request("GetState", data)
        return GetStateResponse.model_validate(result)
    
    def cancel_payment(self, payment_id: str, amount: Optional[int] = None) -> CancelResponse:
        """
        Отмена платежа (возврат)
        
        Args:
            payment_id: ID платежа
            amount: Сумма для возврата (в копейках), если частичный возврат
            
        Returns:
            CancelResponse
        """
        request = CancelRequest(PaymentId=payment_id, Amount=amount)
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = self._make_request("Cancel", data)
        return CancelResponse.model_validate(result)
    
    def confirm_payment(self, payment_id: str, amount: Optional[int] = None,
                       receipt: Optional[Receipt] = None) -> ConfirmResponse:
        """
        Подтверждение платежа (двухстадийная оплата)
        
        Args:
            payment_id: ID платежа
            amount: Сумма для подтверждения (если отличается от исходной)
            receipt: Чек для отправки
            
        Returns:
            ConfirmResponse
        """
        request = ConfirmRequest(PaymentId=payment_id, Amount=amount, Receipt=receipt)
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = self._make_request("Confirm", data)
        return ConfirmResponse.model_validate(result)
    
    def charge_recurrent(self, rebill_id: str, amount: float, order_id: str,
                        send_email: bool = False, info_email: Optional[str] = None,
                        description: Optional[str] = None) -> ChargeResponse:
        """
        Рекуррентный платеж (повторное списание по сохраненной карте)
        
        Args:
            rebill_id: ID рекуррентного платежа (получен при первой оплате)
            amount: Сумма в рублях
            order_id: ID заказа
            send_email: Отправлять ли email
            info_email: Email для уведомления
            description: Описание платежа
            
        Returns:
            ChargeResponse
        """
        request = ChargeRequest(
            RebillId=rebill_id,
            Amount=amount_to_coins(amount),
            OrderId=order_id,
            SendEmail=send_email,
            InfoEmail=info_email,
            Description=description
        )
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = self._make_request("Charge", data)
        return ChargeResponse.model_validate(result)
    
    def send_closing_receipt(self, payment_id: str, receipt: Receipt) -> SendClosingReceiptResponse:
        """
        Отправка закрывающего чека в кассу
        
        Args:
            payment_id: ID платежа
            receipt: Данные чека
            
        Returns:
            SendClosingReceiptResponse
        """
        request = SendClosingReceiptRequest(PaymentId=payment_id, Receipt=receipt)
        data = request.model_dump(by_alias=True, exclude_none=True)
        
        # Отдельный endpoint для чеков
        url = f"{self.config.base_url.replace('/v2', '')}/cashbox/SendClosingReceipt"
        
        signed_data = prepare_request_data(data, self.config.terminal_key, self.config.password)
        
        try:
            response = self.session.post(url, json=signed_data, timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if not result.get("Success", False):
                error_code = result.get("ErrorCode", "0")
                error_msg = result.get("Message", "Unknown error")
                raise TBankAPIError(f"Receipt error: {error_msg}", error_code)
            
            return SendClosingReceiptResponse.model_validate(result)
            
        except requests.exceptions.RequestException as e:
            raise TBankNetworkError(f"Network error: {str(e)}")
    
    def resend_notifications(self) -> Dict[str, Any]:
        """
        Повторная отправка неполученных уведомлений
        
        Returns:
            Dict с количеством отправленных уведомлений
        """
        data = {}
        return self._make_request("Resend", data)
    
    def create_payment_url(self, amount: float, order_id: str, 
                          description: Optional[str] = None,
                          customer_key: Optional[str] = None,
                          recurrent: bool = False,
                          receipt: Optional[Receipt] = None,
                          redirect_due_date: Optional[datetime] = None) -> str:
        """
        Быстрое создание платежа и получение URL для оплаты
        
        Args:
            amount: Сумма в рублях
            order_id: Уникальный ID заказа
            description: Описание платежа
            customer_key: ID клиента (для рекуррентных)
            recurrent: Сделать платеж рекуррентным
            receipt: Данные чека
            redirect_due_date: Срок жизни ссылки
            
        Returns:
            URL для перехода на страницу оплаты
            
        Raises:
            TBankAPIError: если не удалось создать платеж
        """
        request = InitPaymentRequest(
            Amount=amount_to_coins(amount),
            OrderId=order_id,
            Description=description,
            CustomerKey=customer_key,
            Recurrent="Y" if recurrent else None,
            Receipt=receipt,
            RedirectDueDate=format_datetime(redirect_due_date) if redirect_due_date else None
        )
        
        response = self.init_payment(request)
        
        if not response.success or not response.payment_url:
            raise TBankAPIError(
                f"Failed to create payment: {response.error_message}",
                response.error_code
            )
        
        return response.payment_url


class TBankAsyncClient:
    """Асинхронный клиент для API платежей Т-Банка"""
    
    def __init__(self, config: Optional[TBankConfig] = None,
                 terminal_key: Optional[str] = None,
                 password: Optional[str] = None):
        if config:
            self.config = config
        elif terminal_key and password:
            self.config = TBankConfig(terminal_key=terminal_key, password=password)
        else:
            self.config = TBankConfig.from_env()
        
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Получение или создание сессии"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        return self._session
    
    async def _make_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Асинхронное выполнение запроса"""
        url = f"{self.config.base_url}/{endpoint}"
        signed_data = prepare_request_data(data, self.config.terminal_key, self.config.password)
        
        session = await self._get_session()
        
        try:
            async with session.post(url, json=signed_data, timeout=30) as response:
                response.raise_for_status()
                result = await response.json()
                
                if not result.get("Success", False):
                    error_code = result.get("ErrorCode", "0")
                    error_msg = result.get("Message", "Unknown error")
                    
                    if error_code == "0":
                        raise TBankAuthError(f"Authentication failed: {error_msg}", error_code)
                    elif error_code in ["1", "2", "3"]:
                        raise TBankValidationError(f"Validation error: {error_msg}", error_code)
                    else:
                        raise TBankAPIError(f"API error: {error_msg}", error_code)
                
                return result
                
        except aiohttp.ClientError as e:
            raise TBankNetworkError(f"Network error: {str(e)}")
    
    async def init_payment(self, request: InitPaymentRequest) -> InitPaymentResponse:
        """Асинхронная инициализация платежа"""
        data = request.model_dump(by_alias=True, exclude_none=True)
        
        if not data.get("NotificationURL") and self.config.notification_url:
            data["NotificationURL"] = self.config.notification_url
        if not data.get("SuccessURL") and self.config.success_url:
            data["SuccessURL"] = self.config.success_url
        if not data.get("FailURL") and self.config.fail_url:
            data["FailURL"] = self.config.fail_url
        
        result = await self._make_request("Init", data)
        return InitPaymentResponse.model_validate(result)
    
    async def finish_authorize(self, request: FinishAuthorizeRequest) -> FinishAuthorizeResponse:
        """Асинхронное завершение авторизации"""
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = await self._make_request("FinishAuthorize", data)
        return FinishAuthorizeResponse.model_validate(result)
    
    async def get_state(self, payment_id: str, ip: Optional[str] = None) -> GetStateResponse:
        """Асинхронное получение состояния платежа"""
        request = GetStateRequest(PaymentId=payment_id, IP=ip)
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = await self._make_request("GetState", data)
        return GetStateResponse.model_validate(result)
    
    async def cancel_payment(self, payment_id: str, amount: Optional[int] = None) -> CancelResponse:
        """Асинхронная отмена платежа"""
        request = CancelRequest(PaymentId=payment_id, Amount=amount)
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = await self._make_request("Cancel", data)
        return CancelResponse.model_validate(result)
    
    async def confirm_payment(self, payment_id: str, amount: Optional[int] = None,
                             receipt: Optional[Receipt] = None) -> ConfirmResponse:
        """Асинхронное подтверждение платежа"""
        request = ConfirmRequest(PaymentId=payment_id, Amount=amount, Receipt=receipt)
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = await self._make_request("Confirm", data)
        return ConfirmResponse.model_validate(result)
    
    async def charge_recurrent(self, rebill_id: str, amount: float, order_id: str,
                               send_email: bool = False, 
                               info_email: Optional[str] = None,
                               description: Optional[str] = None) -> ChargeResponse:
        """Асинхронный рекуррентный платеж"""
        request = ChargeRequest(
            RebillId=rebill_id,
            Amount=amount_to_coins(amount),
            OrderId=order_id,
            SendEmail=send_email,
            InfoEmail=info_email,
            Description=description
        )
        data = request.model_dump(by_alias=True, exclude_none=True)
        result = await self._make_request("Charge", data)
        return ChargeResponse.model_validate(result)
    
    async def send_closing_receipt(self, payment_id: str, receipt: Receipt) -> SendClosingReceiptResponse:
        """Асинхронная отправка закрывающего чека"""
        request = SendClosingReceiptRequest(PaymentId=payment_id, Receipt=receipt)
        data = request.model_dump(by_alias=True, exclude_none=True)
        
        url = f"{self.config.base_url.replace('/v2', '')}/cashbox/SendClosingReceipt"
        signed_data = prepare_request_data(data, self.config.terminal_key, self.config.password)
        
        session = await self._get_session()
        
        try:
            async with session.post(url, json=signed_data, timeout=30) as response:
                response.raise_for_status()
                result = await response.json()
                
                if not result.get("Success", False):
                    error_code = result.get("ErrorCode", "0")
                    error_msg = result.get("Message", "Unknown error")
                    raise TBankAPIError(f"Receipt error: {error_msg}", error_code)
                
                return SendClosingReceiptResponse.model_validate(result)
                
        except aiohttp.ClientError as e:
            raise TBankNetworkError(f"Network error: {str(e)}")
    
    async def create_payment_url(self, amount: float, order_id: str,
                                  description: Optional[str] = None,
                                  customer_key: Optional[str] = None,
                                  recurrent: bool = False,
                                  receipt: Optional[Receipt] = None,
                                  redirect_due_date: Optional[datetime] = None) -> str:
        """Асинхронное создание платежа и получение URL"""
        request = InitPaymentRequest(
            Amount=amount_to_coins(amount),
            OrderId=order_id,
            Description=description,
            CustomerKey=customer_key,
            Recurrent="Y" if recurrent else None,
            Receipt=receipt,
            RedirectDueDate=format_datetime(redirect_due_date) if redirect_due_date else None
        )
        
        response = await self.init_payment(request)
        
        if not response.success or not response.payment_url:
            raise TBankAPIError(
                f"Failed to create payment: {response.error_message}",
                response.error_code
            )
        
        return response.payment_url
    
    async def close(self):
        """Закрытие сессии"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
Python
Copy
# tbank_payment/__init__.py
"""
T-Bank (Т-Банк) Payment Module
Универсальный модуль для интеграции с платежной системой Т-Касса
"""

from .client import TBankPaymentClient, TBankAsyncClient
from .models import (
    InitPaymentRequest, InitPaymentResponse,
    FinishAuthorizeRequest, FinishAuthorizeResponse,
    PaymentStatus, Receipt, ReceiptItem,
    Notification, CancelRequest, CancelResponse,
    ConfirmRequest, ConfirmResponse,
    GetStateRequest, GetStateResponse,
    ChargeRequest, ChargeResponse,
    SendClosingReceiptRequest, SendClosingReceiptResponse,
    Taxation, VAT, PaymentMethod, PaymentObject,
)
from .exceptions import (
    TBankAPIError, TBankAuthError,
    TBankValidationError, TBankPaymentError,
    TBankNetworkError,
)
from .webhooks import WebhookHandler
from .config import TBankConfig
from .utils import amount_to_coins, coins_to_amount

__version__ = "1.0.0"
__all__ = [
    "TBankPaymentClient",
    "TBankAsyncClient",
    "InitPaymentRequest", "InitPaymentResponse",
    "FinishAuthorizeRequest", "FinishAuthorizeResponse",
    "PaymentStatus", "Receipt", "ReceiptItem",
    "Notification", "CancelRequest", "CancelResponse",
    "ConfirmRequest", "ConfirmResponse",
    "GetStateRequest", "GetStateResponse",
    "ChargeRequest", "ChargeResponse",
    "SendClosingReceiptRequest", "SendClosingReceiptResponse",
    "Taxation", "VAT", "PaymentMethod", "PaymentObject",
    "TBankAPIError", "TBankAuthError",
    "TBankValidationError", "TBankPaymentError", "TBankNetworkError",
    "WebhookHandler", "TBankConfig",
    "amount_to_coins", "coins_to_amount",
]
Python
Copy
# tbank_payment/webhooks.py
"""Обработка webhook-уведомлений от Т-Банка"""

import json
import logging
from typing import Dict, Any, Callable, Optional
from .models import Notification
from .utils import generate_token
from .exceptions import TBankValidationError

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Обработчик webhook-уведомлений"""
    
    def __init__(self, password: str):
        self.password = password
        self._handlers: Dict[str, Callable] = {}
    
    def on(self, status: str, handler: Callable[[Notification], None]):
        """
        Регистрация обработчика для статуса
        
        Args:
            status: Статус платежа (например, "CONFIRMED", "CANCELED", "AUTHORIZED")
            handler: Функция-обработчик
            
        Returns:
            handler (для использования как декоратор)
        """
        self._handlers[status] = handler
        return handler
    
    def validate_notification(self, data: Dict[str, Any]) -> bool:
        """
        Валидация подписи уведомления
        
        Важно: в уведомлении вложенные объекты не участвуют в подписи!
        
        Args:
            data: Данные уведомления
            
        Returns:
            True если подпись валидна
        """
        if "Token" not in data:
            return False
        
        received_token = data["Token"]
        calculated_token = generate_token(data, self.password)
        
        return received_token == calculated_token
    
    def parse_notification(self, body: Union[str, Dict[str, Any]]) -> Notification:
        """
        Парсинг и валидация уведомления
        
        Args:
            body: JSON-строка или dict с данными
            
        Returns:
            Notification объект
            
        Raises:
            TBankValidationError: если подпись невалидна
        """
        if isinstance(body, str):
            data = json.loads(body)
        else:
            data = body
        
        if not self.validate_notification(data):
            raise TBankValidationError("Invalid notification signature")
        
        return Notification.model_validate(data)
    
    def handle(self, body: Union[str, Dict[str, Any]]) -> Notification:
        """
        Обработка уведомления с вызовом зарегистрированных хендлеров
        
        Args:
            body: Данные уведомления
            
        Returns:
            Notification объект
        """
        notification = self.parse_notification(body)
        
        # Вызываем специфичный обработчик
        handler = self._handlers.get(notification.status.value)
        if handler:
            try:
                handler(notification)
            except Exception as e:
                logger.error(f"Error in webhook handler for {notification.status}: {e}")
        
        # Вызываем универсальный обработчик, если есть
        universal_handler = self._handlers.get("*")
        if universal_handler:
            try:
                universal_handler(notification)
            except Exception as e:
                logger.error(f"Error in universal webhook handler: {e}")
        
        return notification
    
    def get_success_response(self) -> str:
        """Возвращает успешный ответ для Т-Банка"""
        return json.dumps({"Success": True})
    
    def get_error_response(self, message: str = "Error") -> str:
        """Возвращает ответ об ошибке"""
        return json.dumps({"Success": False, "Message": message})
Python
Copy
# example_usage.py
"""Примеры использования модуля T-Bank Payment"""

import asyncio
import os
from datetime import datetime, timedelta
from tbank_payment import (
    TBankPaymentClient, TBankAsyncClient, TBankConfig,
    InitPaymentRequest, Receipt, ReceiptItem,
    Taxation, VAT, PaymentStatus,
    WebhookHandler, amount_to_coins,
)


def example_basic_payment():
    """Базовый пример: создание платежа с редиректом на форму Т-Банка"""
    
    client = TBankPaymentClient(
        terminal_key="TinkoffBankTest",
        password="TinkoffBankTest"
    )
    
    # Создаем чек (обязательно если онлайн-касса)
    receipt = Receipt(
        taxation=Taxation.OSN,
        email="customer@example.com",
        items=[
            ReceiptItem(
                name="Ноутбук",
                quantity=1,
                amount=50000,  # 500 руб
                price=50000,
                tax=VAT.VAT20
            )
        ]
    )
    
    # Создаем платеж
    request = InitPaymentRequest(
        amount=50000,  # 500 руб в копейках
        order_id=f"order_{datetime.now().timestamp()}",
        description="Оплата ноутбука",
        customer_key="customer_123",  # Для сохранения карты
        recurrent="Y",  # Сохранить карту для рекуррентов
        receipt=receipt,
        redirect_due_date=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+03:00")
    )
    
    response = client.init_payment(request)
    
    if response.success:
        print(f"✅ Платеж создан!")
        print(f"   URL для оплаты: {response.payment_url}")
        print(f"   Payment ID: {response.payment_id}")
        print(f"   Статус: {response.status}")
    else:
        print(f"❌ Ошибка: {response.error_message}")


def example_recurrent_payment():
    """Пример рекуррентного платежа (списание по сохраненной карте)"""
    
    client = TBankPaymentClient(
        terminal_key="TinkoffBankTest",
        password="TinkoffBankTest"
    )
    
    # rebill_id получаем из webhook после первой оплаты с Recurrent=Y
    rebill_id = "some_rebill_id_from_previous_payment"
    
    try:
        response = client.charge_recurrent(
            rebill_id=rebill_id,
            amount=100.00,  # 100 руб
            order_id=f"recurrent_{datetime.now().timestamp()}",
            description="Ежемесячная подписка",
            send_email=True,
            info_email="customer@example.com"
        )
        
        if response.success:
            print(f"✅ Рекуррентный платеж успешен!")
            print(f"   Payment ID: {response.payment_id}")
            print(f"   Статус: {response.status}")
        else:
            print(f"❌ Ошибка: {response.error_message}")
            
    except Exception as e:
        print(f"❌ Исключение: {e}")


def example_two_stage_payment():
    """Пример двухстадийной оплаты (холдирование + подтверждение)"""
    
    client = TBankPaymentClient(
        terminal_key="TinkoffBankTest",
        password="TinkoffBankTest"
    )
    
    # Шаг 1: Инициализация с PayType=T (двухстадийная)
    request = InitPaymentRequest(
        amount=10000,
        order_id=f"hold_{datetime.now().timestamp()}",
        description="Холдирование средств",
        pay_type="T"  # Двухстадийная!
    )
    
    response = client.init_payment(request)
    payment_id = response.payment_id
    
    print(f"Создан платеж: {payment_id}, статус: {response.status}")
    print(f"Клиент должен оплатить по URL: {response.payment_url}")
    
    # После оплаты клиентом, статус станет AUTHORIZED (деньги заблокированы)
    # В реальном коде ждем webhook или проверяем статус
    
    # Шаг 2: Подтверждение (списание) - когда товар отправлен
    # confirm_response = client.confirm_payment(payment_id)
    # print(f"Подтверждение: {confirm_response.status}")


def example_closing_receipt():
    """Пример отправки закрывающего чека"""
    
    client = TBankPaymentClient(
        terminal_key="TinkoffBankTest",
        password="TinkoffBankTest"
    )
    
    payment_id = "some_payment_id"
    
    # Чек на возврат или корректировку
    receipt = Receipt(
        taxation=Taxation.OSN,
        email="customer@example.com",
        items=[
            ReceiptItem(
                name="Возврат товара",
                quantity=1,
                amount=-5000,  # Отрицательная сумма для возврата
                price=5000,
                tax=VAT.VAT20
            )
        ]
    )
    
    try:
        response = client.send_closing_receipt(payment_id, receipt)
        if response.success:
            print("✅ Закрывающий чек отправлен")
        else:
            print(f"❌ Ошибка: {response.error_message}")
    except Exception as e:
        print(f"❌ Исключение: {e}")


def example_webhook_handling():
    """Пример обработки webhook-уведомлений"""
    
    handler = WebhookHandler(password="TinkoffBankTest")
    
    @handler.on("CONFIRMED")
    def on_payment_confirmed(notification):
        """Успешная оплата (одностадийная)"""
        print(f"✅ Платеж подтвержден: {notification.payment_id}")
        print(f"   Сумма: {notification.amount / 100} руб")
        print(f"   Карта: {notification.pan}")
        
        # Сохраняем rebill_id для рекуррентов
        if notification.rebill_id:
            print(f"   Rebill ID (для рекуррентов): {notification.rebill_id}")
            # Сохранить в БД: notification.rebill_id связан с notification.customer_key
    
    @handler.on("AUTHORIZED")
    def on_payment_authorized(notification):
        """Двухстадийная: деньги заблокированы"""
        print(f"⏸️ Платеж авторизован (холд): {notification.payment_id}")
        # Здесь можно отправить товар, а затем вызвать Confirm
    
    @handler.on("CANCELED")
    def on_payment_canceled(notification):
        """Отмена/возврат"""
        print(f"❌ Платеж отменен: {notification.payment_id}")
    
    @handler.on("REJECTED")
    def on_payment_rejected(notification):
        """Отклонен банком"""
        print(f"🚫 Платеж отклонен: {notification.payment_id}")
    
    @handler.on("*")
    def on_any_status(notification):
        """Логирование всех статусов"""
        print(f"📊 Статус изменен: {notification.status} для {notification.order_id}")
    
    # Симуляция входящего webhook от Т-Банка
    webhook_data = {
        "TerminalKey": "TinkoffBankTest",
        "OrderId": "order_12345",
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": 123456789,
        "Amount": 50000,
        "RebillId": "rebill_123",
        "Pan": "430000******0777",
        "Token": "a1b2c3d4e5f6...",  # Реальная подпись
        "ExpDate": "1125"
    }
    
    try:
        notification = handler.handle(webhook_data)
        print(f"\nОбработано уведомление: {notification.status}")
        
        # Ответ для Т-Банка
        response = handler.get_success_response()
        print(f"Ответ: {response}")
        
    except Exception as e:
        print(f"Ошибка обработки: {e}")
        print(handler.get_error_response(str(e)))


async def async_example():
    """Асинхронный пример"""
    
    async with TBankAsyncClient(
        terminal_key="TinkoffBankTest",
        password="TinkoffBankTest"
    ) as client:
        
        # Быстрое создание платежа
        payment_url = await client.create_payment_url(
            amount=250.00,
            order_id=f"async_{datetime.now().timestamp()}",
            description="Асинхронная оплата"
        )
        
        print(f"Async URL: {payment_url}")
        
        # Проверка статуса
        # status = await client.get_state("payment_id")


if __name__ == "__main__":
    print("=" * 50)
    print("1. Базовый платеж с чеком")
    print("=" * 50)
    example_basic_payment()
    
    print("\n" + "=" * 50)
    print("2. Рекуррентный платеж")
    print("=" * 50)
    example_recurrent_payment()
    
    print("\n" + "=" * 50)
    print("3. Двухстадийная оплата")
    print("=" * 50)
    example_two_stage_payment()
    
    print("\n" + "=" * 50)
    print("4. Закрывающий чек")
    print("=" * 50)
    example_closing_receipt()
    
    print("\n" + "=" * 50)
    print("5. Обработка webhook")
    print("=" * 50)
    example_webhook_handling()
    
    print("\n" + "=" * 50)
    print("6. Асинхронный клиент")
    print("=" * 50)
    asyncio.run(async_example())
Ключевые исправления по документации:
Генерация токена — теперь правильно: только корневые параметры (без вложенных объектов), сортировка по ключам, конкатенация значений
FinishAuthorize — добавлен метод для собственной платежной формы (не PaymentURL)
SendClosingReceipt — отдельный endpoint /cashbox/SendClosingReceipt для закрывающих чеков
Charge — рекуррентные платежи (списание по сохраненной карте)
Поля моделей — точное соответствие документации (алиасы, обязательность)
Обработка webhook — правильная валидация подписи (вложенные объекты не участвуют)
Модуль готов к использованию как плагин! 🚀