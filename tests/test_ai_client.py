import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vk_bot import AIAPIClient, Config


@pytest.mark.asyncio
async def test_analyze_photo():
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text.return_value = json.dumps(
        {"choices": [{"message": {"content": "test prompt"}}]}
    )
    mock_resp.json.return_value = {"choices": [{"message": {"content": "test prompt"}}]}
    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        client = AIAPIClient()
        prompt = await client.analyze_photo("http://test.jpg")
        assert "test prompt" in prompt


@pytest.mark.asyncio
async def test_create_kie_task():
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {"code": 200, "data": {"taskId": "task123"}}
    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        client = AIAPIClient()
        task_id = await client.create_kie_task(
            "kling-2.6/motion-control", {"prompt": "test"}, Config.KLING_API_KEY
        )
        assert task_id == "task123"


@pytest.mark.asyncio
async def test_upload_url_to_kie():
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {"code": 200, "data": {"downloadUrl": "kie_url"}}
    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        client = AIAPIClient()
        url = await client.upload_url_to_kie("http://test.mp4", Config.KLING_API_KEY)
        assert "kie_url" in url


@pytest.mark.asyncio
async def test_upload_file_to_kie(tmp_path):
    test_file = tmp_path / "test.mp4"
    test_file.write_bytes(b"test")
    mock_resp = AsyncMock()
    mock_resp.json.return_value = {"code": 200, "data": {"downloadUrl": "kie_url"}}
    with patch("aiohttp.ClientSession.post", return_value=mock_resp):
        client = AIAPIClient()
        url = await client.upload_file_to_kie(str(test_file), Config.KLING_API_KEY)
        assert "kie_url" in url


@pytest.mark.asyncio
async def test_get_direct_mp4_url():
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.url = "https://example.com/video.mp4"
    with patch("aiohttp.ClientSession.get", return_value=mock_resp):
        client = AIAPIClient()
        url = await client.get_direct_mp4_url("http://vk.doc.mp4")
        assert "mp4" in url
