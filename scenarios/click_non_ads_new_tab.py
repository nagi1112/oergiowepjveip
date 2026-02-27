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
    limit: int = 5,
    dwell_seconds: float = 2.5,
    max_tab_seconds: float = 3.0,
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

    async def click_random_buttons_on_page(tab: Any, remaining_seconds: float) -> None:
        if remaining_seconds <= 0:
            return

        click_count = random.randint(0, 1)
        selector = "button, [role='button'], input[type='button'], input[type='submit'], a[role='button']"

        all_candidates: list[Any] = []
        try:
            select_timeout = max(0.15, min(0.45, remaining_seconds * 0.4))
            elements = await tab.select_all(selector, timeout=select_timeout)
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
                click_timeout = max(0.25, min(1.5, remaining_seconds))
                await asyncio.wait_for(human.click_element(element), timeout=click_timeout)
                clicked_buttons += 1
                if logger:
                    logger.info("Клик по случайной кнопке на открытой вкладке: %s/%s", clicked_buttons, click_count)
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

            await serp_tab.wait(0.45)
            after_tabs = list(browser.tabs)
            new_tabs = [t for t in after_tabs if id(t) not in before_ids]
            tab = new_tabs[-1] if new_tabs else None

            if tab is not None:
                loop = asyncio.get_running_loop()
                tab_started = loop.time()
                opened_tab = tab

                async def process_opened_tab() -> None:
                    await opened_tab.bring_to_front()
                    await opened_tab.wait(0.25)

                    remaining_for_clicks = max(0.0, max_tab_seconds - (loop.time() - tab_started) - 0.05)
                    await click_random_buttons_on_page(opened_tab, remaining_for_clicks)

                    remaining_after_clicks = max(0.0, max_tab_seconds - (loop.time() - tab_started))
                    tab_dwell_seconds = min(random.uniform(2.0, 3.0), dwell_seconds, remaining_after_clicks)
                    if logger:
                        logger.info("Ожидание на открытой вкладке: %.1f сек", tab_dwell_seconds)
                    if tab_dwell_seconds > 0:
                        await asyncio.sleep(tab_dwell_seconds)

                try:
                    await asyncio.wait_for(process_opened_tab(), timeout=max_tab_seconds)
                except asyncio.TimeoutError:
                    if logger:
                        logger.info("Достигнут жёсткий лимит времени на вкладке: %.1f сек", max_tab_seconds)
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
