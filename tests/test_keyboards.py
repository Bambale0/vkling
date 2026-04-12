import json

from vk_bot import Keyboards


def test_keyboards_valid_json():
    keyboards = [
        Keyboards.main_menu(),
        Keyboards.video_options(),
        Keyboards.video_models(),
        Keyboards.photo_models(),
        Keyboards.photo_aspects_keyboard(),
        Keyboards.photo_creation_step(),
        Keyboards.regular_back(),
        Keyboards.motion_control_types(),
        Keyboards.grok_img_keyboard(),
        Keyboards.video_aspects(),
        Keyboards.video_durations(),
    ]
    for kb in keyboards:
        json.loads(kb)  # No exception


def test_keyboards_content_main_menu():
    kb = json.loads(Keyboards.main_menu())
    assert kb["inline"] == True
    assert len(kb["buttons"]) == 3
    assert any(
        "Создать видео" in b["action"]["label"] for row in kb["buttons"] for b in row
    )
