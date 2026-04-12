import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import aiohttp
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tbank import TBankAPI
from vk_bot import (
    AIAPIClient,
    BananaBoomBot,
    Config,
    Database,
    DBStateRule,
    Keyboards,
    NoPayloadRule,
    PayloadContainsRule,
    TextExistsRule,
    UserState,
)


@pytest.fixture(scope="function")
def db(tmp_path):
    """Temporary in-memory or file DB for tests"""
    db_path = tmp_path / "test_vkbanana.db"
    db = Database(str(db_path))
    yield db
    # No explicit cleanup needed, tmp_path handles it


@pytest.fixture
def mock_vk_bot():
    bot = Mock()
    bot.api.messages.send = AsyncMock()
    bot.api.video.get = AsyncMock()
    bot.api.request = AsyncMock()
    return bot


@pytest.fixture
def mock_tbank():
    return Mock(spec=TBankAPI)


@pytest.fixture
def mock_ai_client():
    client = AsyncMock(spec=AIAPIClient)
    return client


@pytest.fixture
def mock_http(httpx_mock):
    return httpx_mock


@pytest.fixture
def banana_bot(db, mock_vk_bot, mock_tbank, mock_ai_client):
    with patch("vk_bot.Bot", return_value=mock_vk_bot), patch(
        "vk_bot.TBankAPI", return_value=mock_tbank
    ), patch("vk_bot.AIAPIClient", return_value=mock_ai_client), patch(
        "vk_bot.Database", return_value=db
    ):
        bot = BananaBoomBot()
        bot.db = db  # Override for direct access
        yield bot
