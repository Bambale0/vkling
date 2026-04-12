import os

from dotenv import load_dotenv

from vk_bot import Config


def test_config_loads_env():
    load_dotenv()
    assert Config.VK_TOKEN is not None
    assert Config.VK_GROUP_ID == 237065803  # From .env
    assert Config.ADMIN_ID == 381643597
    assert Config.WEBHOOK_HOST == "https://vkkling.chillcreative.ru"
    assert Config.KLING_API_KEY == "5dd51c84b904e40e5f285e179d2b93b9"  # Real from .env
    assert Config.TBANK_TERMINAL_KEY == "1774655472125"
    # Test prices dict has expected keys
    assert "photo_generate" in Config.PRICES
    assert Config.PRICES["video_kling_3_std"] == 15
    assert Config.STARTING_BALANCE == 10
