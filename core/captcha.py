from __future__ import annotations

import asyncio
from typing import Any


CAPTCHA_TEXT_MARKERS = (
    "подтвердите, что запросы отправляли вы, а не робот",
    "перемещайте слайдер",
    "нажмите в таком порядке:",
)


async def has_captcha(tab: Any) -> bool:
    try:
        html = (await tab.get_content()).lower()
    except Exception:
        return False

    return any(marker in html for marker in CAPTCHA_TEXT_MARKERS)


async def wait_captcha_clear(tab: Any, timeout: float = 120.0, step: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    started = loop.time()
    while loop.time() - started <= timeout:
        if not await has_captcha(tab):
            return True
        await asyncio.sleep(step)
    return False
