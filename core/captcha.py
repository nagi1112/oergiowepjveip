from __future__ import annotations

import asyncio
from typing import Any


CAPTCHA_MARKERS = (
    "Подтвердите, что запросы отправляли вы, а не робот",
    "Перемещайте слайдер",
    "Нажмите в таком порядке",
    "подтвердите, что запросы отправляли вы, а не робот",
    "перемещайте слайдер",
)


async def has_active_search_tab(tab: Any) -> bool:
    try:
        has_search_cover = await tab.evaluate(
            """
            (() => {
              const covers = Array.from(document.querySelectorAll('span.HeaderNav-TabCover'));
              return covers.some((el) => (el.textContent || '').trim().toLowerCase() === 'поиск');
            })()
            """,
            return_by_value=True,
        )
        if bool(has_search_cover):
            return True
    except Exception:
        pass

    try:
        html = await tab.get_content()
        html_low = html.lower()
        return "headernav-tabcover" in html_low and ">поиск<" in html_low
    except Exception:
        return False


async def has_captcha(tab: Any) -> bool:
    try:
        body_text = await tab.evaluate("document.body ? (document.body.innerText || '') : ''", return_by_value=True)
        normalized_text = str(body_text or "").lower()
        if any(marker.lower() in normalized_text for marker in CAPTCHA_MARKERS):
            return True
    except Exception:
        pass

    has_search = await has_active_search_tab(tab)
    return not has_search


async def wait_captcha_clear(tab: Any, timeout: float = 120.0, step: float = 2.0) -> bool:
    loop = asyncio.get_running_loop()
    started = loop.time()
    while loop.time() - started <= timeout:
        if not await has_captcha(tab):
            return True
        await asyncio.sleep(step)
    return False
