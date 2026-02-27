from __future__ import annotations

from dataclasses import dataclass, field
import importlib
from pathlib import Path
from typing import Any, Iterable, Optional, Union


YANDEX_URL = "https://ya.ru"


def _default_browser_args() -> list[str]:
    return []


@dataclass(slots=True)
class BrowserSettings:
    user_data_dir: Union[Path, str]
    profile_dir_name: str = "chrome_profile"
    headless: bool = False
    no_sandbox: bool = False
    browser_executable_path: Optional[Union[Path, str]] = None
    browser_args: list[str] = field(default_factory=_default_browser_args)
    lang: str = "ru-RU"
    expert: bool = False


def _nodriver() -> Any:
    return importlib.import_module("nodriver")


def _normalize_browser_args(browser_args: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    args: list[str] = []
    for arg in browser_args:
        if arg not in seen:
            seen.add(arg)
            args.append(arg)
    return args


def _normalize_dir_path(path_like: Union[Path, str]) -> Path:
    return Path(path_like).expanduser().resolve()


def make_config(settings: BrowserSettings) -> Any:
    nodriver = _nodriver()
    profile_root = _normalize_dir_path(settings.user_data_dir)
    profile_dir = profile_root / settings.profile_dir_name
    profile_dir.mkdir(parents=True, exist_ok=True)

    executable = None
    if settings.browser_executable_path:
        executable = str(Path(settings.browser_executable_path).expanduser().resolve())

    args = _normalize_browser_args(settings.browser_args)
    return nodriver.Config(
        user_data_dir=str(profile_dir),
        headless=settings.headless,
        no_sandbox=settings.no_sandbox,
        sandbox=not settings.no_sandbox,
        browser_executable_path=executable,
        browser_args=args,
        lang=settings.lang,
        expert=settings.expert,
    )


async def launch_browser(settings: BrowserSettings) -> Any:
    nodriver = _nodriver()
    config = make_config(settings)
    return await nodriver.start(config=config)


async def open_yandex(browser: Any, url: str = YANDEX_URL) -> Any:
    tab = await browser.get(url)
    await tab.wait(0.4)
    return tab


async def shutdown_browser(browser: Any) -> None:
    nodriver = _nodriver()
    try:
        deconstruct_task = nodriver.util.deconstruct_browser(browser)
        if deconstruct_task is not None:
            await deconstruct_task
    except Exception:
        try:
            browser.stop()
        except Exception:
            pass
