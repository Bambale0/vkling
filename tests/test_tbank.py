from unittest.mock import MagicMock, patch

import pytest

from tbank import TBankAPI, requests


@pytest.fixture
def tbank():
    return TBankAPI("test_terminal", "test_secret", "https://test.tbank.ru/v2/")


def test_generate_token_scalar(tbank):
    params = {"Amount": 10000, "OrderId": "test1", "CustomerKey": "user123"}
    token = tbank._generate_token(params)
    assert isinstance(token, str)
    assert len(token) == 64


def test_generate_token_bool(tbank):
    params = {"Recurrent": True, "SendEmail": False}
    token = tbank._generate_token(params)
    assert token


def test_generate_token_ignore_dict(tbank):
    params = {"Data": {"key": "value"}, "Receipt": [{"Amount": 100}]}
    token = tbank._generate_token(params)


@patch("tbank.requests.post")
def test_init_payment_success(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "Success": True,
        "PaymentId": "pay123",
        "PaymentURL": "https://pay.test",
    }
    mock_post.return_value = mock_resp
    result = tbank.init_payment(amount=10000, order_id="test1", description="Test")
    assert result["Success"]


@patch("tbank.requests.post")
def test_init_payment_business_fail(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": False, "ErrorCode": "40001"}
    mock_post.return_value = mock_resp
    result = tbank.init_payment(amount=10000, order_id="test1", description="Test")
    assert not result["Success"]


@patch("tbank.requests.post")
def test_init_payment_http_fail(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_post.return_value = mock_resp
    result = tbank.init_payment(amount=10000, order_id="test1", description="Test")
    assert result is None


@patch("tbank.requests.post")
def test_confirm(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": True}
    mock_post.return_value = mock_resp
    result = tbank.confirm("pay123")
    assert result["Success"]


@patch("tbank.requests.post")
def test_cancel(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": True}
    mock_post.return_value = mock_resp
    result = tbank.cancel("pay123")
    assert result["Success"]


# Add similar for other methods
@patch("tbank.requests.post")
def test_finish_authorize(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": True}
    mock_post.return_value = mock_resp
    result = tbank.finish_authorize("pay123")
    assert result["Success"]


@patch("tbank.requests.post")
def test_get_state(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Status": "CONFIRMED"}
    mock_post.return_value = mock_resp
    result = tbank.get_state("pay123")
    assert result["Status"] == "CONFIRMED"


@patch("tbank.requests.post")
def test_get_card_list(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Cards": []}
    mock_post.return_value = mock_resp
    result = tbank.get_card_list("customer1")
    assert "Cards" in result


@patch("tbank.requests.post")
def test_remove_card(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": True}
    mock_post.return_value = mock_resp
    result = tbank.remove_card("card1")
    assert result["Success"]


@patch("tbank.requests.post")
def test_resend(mock_post, tbank):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": True}
    mock_post.return_value = mock_resp
    result = tbank.resend("pay123")
    assert result["Success"]


@patch("tbank.requests.post")
def test_send_closing_receipt(mock_post, tbank):
    receipt = {"Items": []}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"Success": True}
    mock_post.return_value = mock_resp
    result = tbank.send_closing_receipt("pay123", receipt)
    assert result["Success"]


def test_build_receipt():
    receipt = TBankAPI.build_receipt(
        "email@test.com",
        "+7...",
        [{"Name": "test", "Price": 100, "Quantity": 1, "Amount": 100, "Tax": "none"}],
    )
    assert "Email" in receipt
