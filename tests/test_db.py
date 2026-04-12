import json

import pytest

from vk_bot import Database


@pytest.mark.parametrize("user_id", [123, 456])
def test_get_or_create_user(db, user_id):
    user = db.get_or_create_user(user_id)
    assert user["user_id"] == user_id
    assert user["balance"] == 10
    assert user["is_blocked"] == 0
    assert user["block_reason"] is None

    # Second call returns same user
    user2 = db.get_or_create_user(user_id)
    assert user2["user_id"] == user_id
    assert user2["balance"] == 10


def test_update_balance_success(db):
    user_id = 123
    db.get_or_create_user(user_id)
    success = db.update_balance(user_id, 5, "test +")
    assert success is True
    balance = db.get_balance(user_id)
    assert balance == 15

    # Check transaction
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT amount, reason FROM transactions WHERE user_id = ?", (user_id,)
    )
    trans = cursor.fetchone()
    assert trans[0] == 5
    assert "test +" in trans[1]
    conn.close()


def test_update_balance_negative_success(db):
    user_id = 123
    db.get_or_create_user(user_id)
    db.update_balance(user_id, 3, "test -")
    balance = db.get_balance(user_id)
    assert balance == 13
    success = db.update_balance(user_id, -5, "test --")
    assert success is True
    assert db.get_balance(user_id) == 8


def test_update_balance_negative_fail(db):
    user_id = 123
    db.get_or_create_user(user_id)
    success1 = db.update_balance(user_id, -15, "fail")
    assert success1 is False
    assert db.get_balance(user_id) == 10  # Didn't update
    success2 = db.update_balance(user_id, -1, "fail2")
    assert success2 is True  # 10-1=9 >=0
    assert db.get_balance(user_id) == 9


def test_get_balance_nonexistent(db):
    assert db.get_balance(999) == 0


def test_set_get_clear_state(db):
    user_id = 123
    data = {"key": "value"}
    db.set_state(user_id, "test_state", data)
    state, retrieved_data = db.get_state(user_id)
    assert state == "test_state"
    assert retrieved_data == data

    # Update
    new_data = {"key2": 42}
    db.set_state(user_id, "new_state", new_data)
    state, retrieved_data = db.get_state(user_id)
    assert state == "new_state"
    assert retrieved_data == new_data

    # Clear
    db.clear_state(user_id)
    state, retrieved_data = db.get_state(user_id)
    assert state is None
    assert retrieved_data == {}


def test_create_task(db):
    user_id = 123
    db.get_or_create_user(user_id)
    task_id = db.create_task(user_id, "test", "model", "prompt", 10, ["ref1"])
    assert isinstance(task_id, int) and task_id > 0

    details = db.get_task_details(task_id)
    assert details["user_id"] == user_id
    assert details["cost"] == 10
    assert details["status"] == "pending"

    user_task = db.get_task_user(task_id)
    assert user_task == user_id


def test_update_task_status(db):
    user_id = 123
    task_id = db.create_task(user_id, "test", "model", "prompt", 10)
    db.update_task_status(task_id, "processing", api_task_id="api123")
    details = db.get_task_details(task_id)
    assert details["status"] == "processing"
    # Verify api_task_id directly
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT api_task_id FROM generation_tasks WHERE task_id=?", (task_id,)
    )
    api_id = cursor.fetchone()[0]
    assert api_id == "api123"
    conn.close()

    db.update_task_status(task_id, "completed", result_url="url")
    details = db.get_task_details(task_id)
    assert details["status"] == "completed"
    assert details["result_url"] == "url"

    db.update_task_status(task_id, "failed", error_message="err")
    details = db.get_task_details(task_id)
    assert details["status"] == "failed"
    assert details["error_message"] == "err"


def test_payments(db):
    user_id = 123
    order_id = "test_order"
    payment_id = db.create_pending_payment(user_id, order_id, 100)
    assert isinstance(payment_id, int)

    payment = db.get_payment_by_order_id(order_id)
    assert payment["user_id"] == user_id
    assert payment["order_id"] == order_id
    assert payment["amount_rub"] == 100
    assert payment["status"] == "pending"

    tbank_id = "tbank123"
    db.update_payment_tbank_id(payment_id, tbank_id)
    payment2 = db.get_payment_by_tbank_id(tbank_id)
    assert payment2["tbank_payment_id"] == tbank_id

    db.update_payment_status(payment_id, "confirmed")
    payment3 = db.get_payment_by_order_id(order_id)
    assert payment3["status"] == "confirmed"


def test_init_db_tables(db):
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cursor.fetchall()}
    expected = {
        "users",
        "generation_tasks",
        "transactions",
        "user_states",
        "payments",
        "sqlite_sequence",
    }
    assert expected.issubset(tables)
    conn.close()
