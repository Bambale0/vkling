from unittest.mock import AsyncMock

import pytest

from tests.conftest import db
from vk_bot import (
    DBStateRule,
    Message,
    NoPayloadRule,
    PayloadContainsRule,
    TextExistsRule,
)


@pytest.mark.asyncio
async def test_text_exists_rule():
    rule = TextExistsRule()
    msg_text = Message(
        text="hello",
        from_id=123,
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    msg_no_text = Message(
        text="",
        from_id=123,
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    assert await rule.check(msg_text)
    assert not await rule.check(msg_no_text)


@pytest.mark.asyncio
async def test_no_payload_rule():
    rule = NoPayloadRule()
    msg_no_payload = Message(
        payload=None,
        text="test",
        from_id=123,
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    msg_payload = Message(
        payload="{}",
        text="test",
        from_id=123,
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    assert await rule.check(msg_no_payload)
    assert not await rule.check(msg_payload)


@pytest.mark.asyncio
async def test_payload_contains_rule():
    rule = PayloadContainsRule("cmd")
    msg_cmd = Message(
        payload='{"cmd": "test"}',
        text="test",
        from_id=123,
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    msg_no_cmd = Message(
        payload='{"other": "test"}',
        text="test",
        from_id=123,
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    assert await rule.check(msg_cmd)
    assert not await rule.check(msg_no_cmd)


@pytest.mark.asyncio
async def test_db_state_rule(db):
    rule_idle = DBStateRule(db, "idle")
    # Set state
    db.set_state(123, "idle")
    msg = Message(
        from_id=123,
        text="test",
        peer_id=123,
        id=1,
        date=1,
        version=1,
        conversation_message_id=1,
        out=0,
    )
    assert await rule_idle.check(msg)
    db.set_state(123, "other")
    assert not await rule_idle.check(msg)
