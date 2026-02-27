from __future__ import annotations

import asyncio
import random
from typing import Any, cast
from urllib.parse import urlparse


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


async def click_non_ads_in_new_tabs(
    browser: Any,
    serp_tab: Any,
    human: Any,
    parsed_results: list[dict[str, Any]],
    *,
    limit: int = 2,
    dwell_seconds: float = 3.0,
    logger: Any = None,
) -> int:
    allowed_domains: set[str] = set()

    for item in parsed_results:
        if item.get("is_ad"):
            continue
        url = str(item.get("url") or "")
        if not url.startswith("http"):
            continue
        domain = str(item.get("domain") or _domain(url))
        if domain:
            allowed_domains.add(domain)

    anchors = await serp_tab.select_all("a[href^='http']", timeout=5)
    candidates: list[Any] = []
    seen_domains: set[str] = set()
    for anchor in anchors:
        href = anchor.attrs.get("href") if anchor and anchor.attrs else None
        if not href:
            continue
        href = str(href)
        domain = _domain(href)
        if not domain or domain in seen_domains:
            continue
        if "yandex.ru" in domain or "ya.ru" in domain:
            continue
        if allowed_domains and domain not in allowed_domains:
            continue
        seen_domains.add(domain)
        candidates.append(anchor)
        if len(candidates) >= limit:
            break

    if logger:
        logger.info("Сценарий non-ads: кандидатных ссылок=%s", len(candidates))

    async def click_random_buttons_on_page(tab: Any) -> None:
        click_count = random.randint(2, 3)
        selectors = [
            "button",
            "[role='button']",
            "input[type='button']",
            "input[type='submit']",
            "a[role='button']",
        ]

        all_candidates: list[Any] = []
        for selector in selectors:
            try:
                elements = await tab.select_all(selector, timeout=2)
            except Exception:
                elements = []
            for element in cast(list[Any], elements):
                all_candidates.append(element)

        random.shuffle(all_candidates)
        clicked_buttons = 0
        for element in all_candidates:
            if clicked_buttons >= click_count:
                break
            try:
                await human.click_element(element)
                clicked_buttons += 1
                if logger:
                    logger.info("Клик по случайной кнопке на открытой вкладке: %s/%s", clicked_buttons, click_count)
                await asyncio.sleep(random.uniform(2.0, 4.0))
            except Exception:
                continue

        if logger:
            logger.info("Случайных кликов по кнопкам выполнено: %s", clicked_buttons)

    clicked = 0
    for anchor in candidates:
        tab = None
        try:
            href = str(anchor.attrs.get("href") or "")
            if logger:
                logger.info("Физический Ctrl+Click по ссылке: %s", href)

            before_tabs = list(browser.tabs)
            before_ids = {id(t) for t in before_tabs}

            await serp_tab.bring_to_front()
            await serp_tab.wait(0.2)
            await human.click_element_new_tab(anchor)

            await serp_tab.wait(1.0)
            after_tabs = list(browser.tabs)
            new_tabs = [t for t in after_tabs if id(t) not in before_ids]
            tab = new_tabs[-1] if new_tabs else None

            if tab is not None:
                await tab.bring_to_front()
                await tab.wait(1.2)
                await click_random_buttons_on_page(tab)
            await asyncio.sleep(dwell_seconds)
            clicked += 1
        except Exception as exc:
            if logger:
                logger.info("Ошибка физического открытия ссылки: %s", exc)
        finally:
            if tab is not None:
                try:
                    await tab.close()
                except Exception:
                    pass
            try:
                await serp_tab.bring_to_front()
                await serp_tab.wait(0.3)
            except Exception:
                pass

    return clicked
