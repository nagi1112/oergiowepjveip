from __future__ import annotations

import asyncio
import importlib
import os
import random
from contextlib import nullcontext
from pathlib import Path
import sys
from typing import Any
from urllib.parse import unquote, urlsplit

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from core.browser import BrowserSettings, launch_browser, shutdown_browser
    from core.human_actions import HumanActions, HumanProfile
    from core.captcha import has_captcha
    from core.captcha_solver_nodriver import CaptchaSolverNodriver
    from core.pars_page import find_domens
    from scenarios.click_non_ads_new_tab import click_non_ads_in_new_tabs
    from core.utils import setup_logging
else:
    from .browser import BrowserSettings, launch_browser, shutdown_browser
    from .human_actions import HumanActions, HumanProfile
    from .captcha import has_captcha
    from .captcha_solver_nodriver import CaptchaSolverNodriver
    from .pars_page import find_domens
    from scenarios.click_non_ads_new_tab import click_non_ads_in_new_tabs
    from .utils import setup_logging


DEFAULT_USER_DATA_DIR = Path("user_data_proxy")
DEFAULT_PROXY_PROFILE_DIR_NAME = "chrome_profile_proxy"
DEFAULT_PROXY = "user184655:9nft6e@166.1.226.195:3087"
DEFAULT_HEADLESS = False
DEFAULT_MOUSE_VISUAL_DEBUG = False
DEFAULT_QUERIES: list[str] = [
    "тест",
    "купить машину",
    "купить машину с пробегом",
    "автосалон официальный дилер",
    "кредит на автомобиль онлайн",
    "авто в лизинг",
    "срочный выкуп авто",
    "проверить авто по вин коду",
    "запчасти интернет магазин",
    "шиномонтаж рядом со мной",
    "купить квартиру",
    "снять квартиру",
    "купить студию в новостройке",
    "вторичка купить недорого",
    "квартиры посуточно",
    "загородные дома купить",
    "коттедж аренда",
    "коммерческая недвижимость",
    "ипотека калькулятор",
    "кредит наличными",
    "открыть вклад",
    "кредитная карта без процентов",
    "рефинансирование кредитов",
    "овердрафт на карту",
    "инвестиции для начинающих",
    "брокерский счет открыть",
    "курс доллара",
    "курс евро",
    "погода москва",
    "погода санкт петербург",
    "пробки москва сейчас",
    "новости россии",
    "новости технологий",
    "новости [название города/района]",
    "курс валют цб на сегодня",
    "рецепты ужин",
    "доставка еды",
    "пицца рядом",
    "суши вок доставка",
    "заказать роллы на дом",
    "продукты с доставкой на дом",
    "готовые обеды с доставкой",
    "бургеры доставка круглосуточно",
    "такси заказать",
    "билеты на поезд",
    "авиабилеты дешево",
    "отели сочи",
    "туры в турцию",
    "аренда авто без водителя",
    "железнодорожные билеты туда и обратно",
    "горящие туры из москвы",
    "отели все включено",
    "экскурсии индивидуальные",
    "страховка осаго",
    "каско онлайн",
    "страхование ипотеки",
    "страхование путешественников",
    "осаго рассчитать стоимость полиса",
    "дмс для иностранцев",
    "работа удаленно",
    "вакансии python",
    "курсы английского",
    "школа программирования",
    "работа для студентов с ежедневной оплатой",
    "фриланс биржа",
    "курсы повышения квалификации",
    "онлайн обучение с сертификатом",
    "тренинг по продажам",
    "купить ноутбук",
    "купить смартфон",
    "наушники беспроводные",
    "телевизор 55 дюймов",
    "ноутбук для игр купить",
    "сравнение смартфонов 2024",
    "apple iphone цена",
    "умные часы купить",
    "пылесос робот отзывы",
    "стиральная машина",
    "холодильник купить",
    "мебель для кухни",
    "ремонт квартиры",
    "строительные материалы",
    "кухонный гарнитур на заказ",
    "диван угловой недорого",
    "квартира под ключ ремонт",
    "ламинат купить в интернет магазине",
    "сантехника официальный сайт",
    "стоматология рядом",
    "запись к врачу",
    "анализы сдать",
    "фитнес клуб",
    "йога для начинающих",
    "клиника пластической хирургии",
    "мрт обследование цена",
    "лечение зубов под ключ",
    "персональный тренер в тренажерный зал",
    "диета для похудения меню",
    "куда сходить москва",
    "афиша кино",
    "сериал смотреть",
    "музыка онлайн",
    "книги купить",
    "квесты для двоих",
    "билеты в театр",
    "купить подписку на кино",
    "аудиокниги скачать бесплатно",
    "юридическая консультация",
    "бухгалтерские услуги",
    "доставка цветов",
    "подарки на день рождения",
    "вызов сантехника на дом",
    "ремонт стиральных машин на дому",
    "клининг квартиры цены",
    "букет цветов с доставкой круглосуточно",
    "именные подарки с гравировкой",
]


def _parse_proxy_url(proxy: str) -> tuple[str, str, int, str | None, str | None]:
    raw_proxy = proxy.strip()
    if not raw_proxy:
        raise ValueError("Пустая строка прокси")

    if "://" not in raw_proxy:
        raw_proxy = f"http://{raw_proxy}"

    parsed = urlsplit(raw_proxy)
    if not parsed.hostname or not parsed.port:
        raise ValueError(f"Некорректный формат прокси: {proxy}")

    scheme = parsed.scheme or "http"
    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None
    return scheme, parsed.hostname, parsed.port, username, password


def build_proxy_browser_args(proxy: str, user_data_dir: Path) -> list[str]:
    scheme, host, port, username, password = _parse_proxy_url(proxy)
    _ = (username, password, user_data_dir)
    return [f"--proxy-server={scheme}://{host}:{port}"]


def _fetch_cdp() -> Any:
    return importlib.import_module("nodriver.cdp.fetch")


async def enable_proxy_auth(tab: Any, proxy: str, logger: Any) -> None:
    _scheme, _host, _port, username, password = _parse_proxy_url(proxy)
    if not username or not password:
        return

    fetch = _fetch_cdp()

    async def _on_auth_required(event: Any) -> None:
        try:
            await tab.send(
                fetch.continue_with_auth(
                    event.request_id,
                    fetch.AuthChallengeResponse(
                        response="ProvideCredentials",
                        username=username,
                        password=password,
                    ),
                )
            )
        except Exception as exc:
            logger.info("Не удалось отправить proxy auth credentials: %s", exc)

    async def _on_request_paused(event: Any) -> None:
        try:
            await tab.send(fetch.continue_request(event.request_id))
        except Exception as exc:
            logger.info("Не удалось продолжить paused request: %s", exc)

    tab.add_handler(fetch.AuthRequired, _on_auth_required)
    tab.add_handler(fetch.RequestPaused, _on_request_paused)
    await tab.send(fetch.enable(handle_auth_requests=True))
    logger.info("Proxy auth handler активирован")


def _install_unraisable_noise_filter() -> None:
    original_hook = sys.unraisablehook

    def filtered_hook(unraisable: Any) -> None:
        message = str(getattr(unraisable, "exc_value", ""))
        object_repr = repr(getattr(unraisable, "object", ""))
        if "I/O operation on closed pipe" in message and "_ProactorBasePipeTransport" in object_repr:
            return
        original_hook(unraisable)

    sys.unraisablehook = filtered_hook


def _runtime_display_context() -> Any:
    if not sys.platform.startswith("linux"):
        return nullcontext()

    if os.environ.get("DISPLAY"):
        return nullcontext()

    try:
        from pyvirtualdisplay import Display
    except Exception as exc:
        raise RuntimeError(
            "Для запуска на Linux установите pyvirtualdisplay: pip install pyvirtualdisplay"
        ) from exc

    return Display(visible=0, size=(1920, 1080))


async def find_search_input(tab: Any) -> tuple[Any, str | None]:
    selectors = [
        "textarea#text",
        "input[name='text']",
        "input[aria-label*='Запрос']",
        "input[type='search']",
        "input[name='q']",
    ]
    for selector in selectors:
        element = await tab.select(selector, timeout=3)
        if element:
            return element, selector
    return None, None


async def find_submit_button(tab: Any) -> Any:
    selectors = [
        "button.search3__button.search3__button_icon_yes.mini-suggest__button",
        "button[type='submit']",
        "button[aria-label*='Найти']",
    ]
    for selector in selectors:
        element = await tab.select(selector, timeout=2)
        if element:
            return element
    return None


async def find_clear_button(tab: Any) -> Any:
    selectors = [
        "button.HeaderForm-Clear",
        "button.mini-suggest__input-clear",
        "button.HeaderFormActions-Item.HeaderForm-Clear",
    ]
    for selector in selectors:
        element = await tab.select(selector, timeout=2)
        if element:
            return element
    return None


async def read_input_value(element: Any) -> str:
    try:
        value = await element.apply("(el) => el.value || ''")
        return str(value or "")
    except Exception:
        return ""


async def wait_input_value(element: Any, expected: str, timeout: float = 5.0) -> bool:
    loop = asyncio.get_running_loop()
    started = loop.time()
    expected_norm = " ".join(expected.split()).lower()

    while loop.time() - started < timeout:
        current = await read_input_value(element)
        current_norm = " ".join(current.split()).lower()
        if current_norm == expected_norm:
            return True
        await asyncio.sleep(0.15)
    return False


async def is_serp_loaded(tab: Any) -> bool:
    try:
        url = await tab.evaluate("window.location.href", return_by_value=True)
        if isinstance(url, str) and "yandex.ru/search" in url:
            return True
    except Exception:
        pass

    try:
        html = await tab.get_content()
        markers = ("serp-item", "serp-list", "main__content", "organic")
        return any(marker in html for marker in markers)
    except Exception:
        return False


async def wait_captcha_with_rechecks(tab: Any, logger: Any, timeout: float = 180.0, step: float = 7.0) -> bool:
    loop = asyncio.get_running_loop()
    started = loop.time()
    reloaded_once = False

    while loop.time() - started < timeout:
        if not await has_captcha(tab):
            return True

        elapsed = int(loop.time() - started)
        logger.info("Капча всё ещё активна (%s сек), повторная проверка через %s сек...", elapsed, int(step))
        await tab.wait(step)

        if not reloaded_once:
            try:
                logger.info("Капча не ушла, делаю reload страницы перед новой проверкой")
                await tab.reload()
                await tab.wait(1.2)
                reloaded_once = True
            except Exception as exc:
                logger.info("Не удалось выполнить reload при проверке капчи: %s", exc)
                reloaded_once = True
            continue

        logger.info("Капча всё ещё активна после reload, жду ручное решение и проверяю HTML каждые 5 сек...")
        while True:
            try:
                html = (await tab.get_content()).lower()
            except Exception:
                html = ""

            has_captcha_marker = (
                "подтвердите, что запросы отправляли вы, а не робот" in html
                or "перемещайте слайдер" in html
                or "нажмите в таком порядке" in html
            )

            if not has_captcha_marker and not await has_captcha(tab):
                logger.info("Капча пройдена вручную, продолжаю работу")
                return True

            elapsed = int(loop.time() - started)
            logger.info("Капча всё ещё активна (%s сек), повторная HTML-проверка через 5 сек...", elapsed)
            await tab.wait(5)

    return False


def _is_stale_node_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "no node with given id found" in message
        or "does not belong to the document" in message
        or "code: -32000" in message
    )


async def submit_query(tab: Any, element: Any, human: HumanActions, logger: Any) -> None:
    submit_button = await find_submit_button(tab)
    if submit_button:
        logger.info("Явный submit: клик по кнопке Найти")
        await human.click_element(submit_button)
        await tab.wait(1.2)

        if await is_serp_loaded(tab):
            return

    try:
        await human.press_enter(element)
    except Exception as exc:
        if _is_stale_node_error(exc):
            logger.info("Элемент устарел после submit, переищу поле и повторю Enter")
            refreshed_input, _ = await find_search_input(tab)
            if refreshed_input:
                try:
                    await human.press_enter(refreshed_input)
                except Exception as second_exc:
                    if _is_stale_node_error(second_exc):
                        logger.info("Поле снова устарело после submit — вероятно редирект/капча, продолжаю без повторного Enter")
                    else:
                        raise
        else:
            raise

    await tab.wait(1.2)

    if await is_serp_loaded(tab):
        return

    logger.info("Кнопка и Enter не сработали, fallback: submit формы")
    try:
        await element.apply("(el) => { const form = el.closest('form'); if (form) form.submit(); }")
        await tab.wait(1.2)
    except Exception:
        pass


async def wait_and_parse_results(tab: Any, timeout: float = 20.0) -> list[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    started = loop.time()
    last_results: list[dict[str, Any]] = []

    while loop.time() - started < timeout:
        html = await tab.get_content()
        results = find_domens(html)
        if results:
            return results
        last_results = results
        await tab.wait(0.5)

    return last_results


async def smoke_open_and_close(user_data_dir: Path, headless: bool = False) -> None:
    logger = setup_logging()
    resolved_user_data_dir = Path(user_data_dir).expanduser().resolve()
    proxy_args = build_proxy_browser_args(DEFAULT_PROXY, resolved_user_data_dir)
    settings = BrowserSettings(
        user_data_dir=resolved_user_data_dir,
        profile_dir_name=DEFAULT_PROXY_PROFILE_DIR_NAME,
        headless=headless,
        browser_args=proxy_args,
    )
    human_profile = HumanProfile()
    human_profile.mouse_visual_debug = DEFAULT_MOUSE_VISUAL_DEBUG
    human_profile.mouse_pause_min *= 1.2
    human_profile.mouse_pause_max *= 1.2
    human_profile.pre_click_pause_min *= 1.2
    human_profile.pre_click_pause_max *= 1.2
    human_profile.post_click_pause_min *= 1.2
    human_profile.post_click_pause_max *= 1.2
    human_profile.key_delay_min *= 1.2
    human_profile.key_delay_max *= 1.2
    human = HumanActions(profile=human_profile, logger=logger)

    browser = await launch_browser(settings)
    try:
        tab = browser.main_tab
        await enable_proxy_auth(tab, DEFAULT_PROXY, logger)
        await tab.wait(0.5)
        await tab.get("https://ya.ru/")
        await tab.wait(1.0)
        logger.info("Профиль: %s", Path(settings.user_data_dir).resolve())
        queries_to_run = list(DEFAULT_QUERIES)
        random.shuffle(queries_to_run)
        logger.info("Всего запросов в очереди: %s (случайный порядок, без повторов)", len(queries_to_run))

        for index, query in enumerate(queries_to_run, start=1):
            try:
                if index > 1:
                    clear_button = await find_clear_button(tab)
                    if clear_button:
                        logger.info("[%s/%s] Нажимаю крестик очистки", index, len(queries_to_run))
                        await human.click_element(clear_button)
                        await tab.wait(0.4)

                element, selector = await find_search_input(tab)
                logger.info("[%s/%s] Input найден: %s", index, len(queries_to_run), bool(element))
                logger.info("[%s/%s] Селектор: %s", index, len(queries_to_run), selector)
                if not element:
                    logger.info("[%s/%s] Поле поиска не найдено, пропускаю запрос: %s", index, len(queries_to_run), query)
                    continue

                await human.type_text(element, query, clear_before=True)
                if not await wait_input_value(element, query, timeout=5.0):
                    current_value = await read_input_value(element)
                    logger.info("[%s/%s] Значение поля не стабилизировалось. Текущее: %s", index, len(queries_to_run), current_value)

                await submit_query(tab, element, human, logger)

                if await has_captcha(tab):
                    solver = CaptchaSolverNodriver(tab, human, logger)
                    if await solver.solve_smart(max_attempts=3):
                        logger.info("[%s/%s] Капча успешно решена", index, len(queries_to_run))
                    else:
                        logger.warning("[%s/%s] Не удалось решить капчу за попытки", index, len(queries_to_run))
                        logger.info("[%s/%s] Перехожу к ручному ожиданию прохождения капчи", index, len(queries_to_run))
                        solved = await wait_captcha_with_rechecks(tab, logger, timeout=180, step=7)
                        if not solved:
                            logger.warning("[%s/%s] Капча не пройдена (таймаут), пропускаю запрос", index, len(queries_to_run))
                            continue

                logger.info("[%s/%s] Запрос введён: %s", index, len(queries_to_run), query)
                results = await wait_and_parse_results(tab, timeout=20)
                logger.info("[%s/%s] Результатов спарсено: %s", index, len(queries_to_run), len(results))
                for item in results[:10]:
                    logger.info("rank=%s domain=%s is_ad=%s", item.get("rank"), item.get("domain"), item.get("is_ad"))

                non_ads_limit = random.randint(2, 3)
                logger.info("[%s/%s] Лимит non-ads на этот запрос: %s", index, len(queries_to_run), non_ads_limit)
                clicked = await click_non_ads_in_new_tabs(
                    browser,
                    tab,
                    human,
                    results,
                    limit=non_ads_limit,
                    dwell_seconds=random.uniform(3.0, 4.0),
                    logger=logger,
                )
                logger.info("[%s/%s] Сценарий завершен: открыто не-рекламных ссылок=%s", index, len(queries_to_run), clicked)
                await tab.wait(0.8)
            except Exception as exc:
                logger.info("[%s/%s] Ошибка на запросе '%s': %s", index, len(queries_to_run), query, exc)
                await tab.wait(1.0)
                continue
    finally:
        await shutdown_browser(browser)
        await asyncio.sleep(0.25)
        logger.info("Браузер закрыт")


def main() -> None:
    _install_unraisable_noise_filter()
    with _runtime_display_context():
        asyncio.run(
            smoke_open_and_close(
                user_data_dir=DEFAULT_USER_DATA_DIR,
                headless=DEFAULT_HEADLESS,
            )
        )


if __name__ == "__main__":
    main()
