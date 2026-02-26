from __future__ import annotations

import asyncio
import importlib
import random
from dataclasses import dataclass
from typing import Any, Optional

from .utils import async_sleep, jitter


@dataclass(slots=True)
class HumanProfile:
    mouse_steps_min: int = 18
    mouse_steps_max: int = 42
    mouse_pause_min: float = 0.003
    mouse_pause_max: float = 0.02
    pre_click_pause_min: float = 0.05
    pre_click_pause_max: float = 0.18
    post_click_pause_min: float = 0.08
    post_click_pause_max: float = 0.32
    key_delay_min: float = 0.05
    key_delay_max: float = 0.16
    key_thinking_pause_chance: float = 0.12
    key_thinking_pause_min: float = 0.25
    key_thinking_pause_max: float = 0.9


class HumanActions:
    def __init__(self, profile: Optional[HumanProfile] = None) -> None:
        self.profile = profile or HumanProfile()
        self._cursor_positions: dict[int, tuple[float, float]] = {}

    def _tab_key(self, tab: Any) -> int:
        return id(tab)

    def _nodriver(self) -> Any:
        return importlib.import_module("nodriver")

    def _get_cursor(self, tab: Any) -> tuple[float, float]:
        return self._cursor_positions.get(self._tab_key(tab), (0.0, 0.0))

    def _set_cursor(self, tab: Any, x: float, y: float) -> None:
        self._cursor_positions[self._tab_key(tab)] = (x, y)

    async def _dispatch_mouse_move(self, tab: Any, x: float, y: float) -> None:
        nodriver = self._nodriver()
        await tab.send(nodriver.cdp.input_.dispatch_mouse_event("mouseMoved", x=float(x), y=float(y)))

    def _bezier_point(
        self,
        t: float,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        p3: tuple[float, float],
    ) -> tuple[float, float]:
        u = 1.0 - t
        x = (u ** 3) * p0[0] + 3 * (u ** 2) * t * p1[0] + 3 * u * (t ** 2) * p2[0] + (t ** 3) * p3[0]
        y = (u ** 3) * p0[1] + 3 * (u ** 2) * t * p1[1] + 3 * u * (t ** 2) * p2[1] + (t ** 3) * p3[1]
        return x, y

    def _control_points(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dist = max((dx * dx + dy * dy) ** 0.5, 1.0)
        spread = max(12.0, min(dist * 0.35, 180.0))

        cp1 = (
            start[0] + dx * random.uniform(0.2, 0.35) + random.uniform(-spread, spread),
            start[1] + dy * random.uniform(0.2, 0.35) + random.uniform(-spread, spread),
        )
        cp2 = (
            start[0] + dx * random.uniform(0.65, 0.85) + random.uniform(-spread, spread),
            start[1] + dy * random.uniform(0.65, 0.85) + random.uniform(-spread, spread),
        )
        return cp1, cp2
    

    async def move_mouse_to(self, tab: Any, target_x: float, target_y: float, steps: Optional[int] = None) -> None:
        start_x, start_y = self._get_cursor(tab)
        step_count = steps or random.randint(self.profile.mouse_steps_min, self.profile.mouse_steps_max)
        step_count = max(1, step_count)

        p0 = (float(start_x), float(start_y))
        p3 = (float(target_x), float(target_y))
        p1, p2 = self._control_points(p0, p3)

        for step in range(1, step_count + 1):
            t = step / step_count
            x, y = self._bezier_point(t, p0, p1, p2, p3)
            x += random.uniform(-0.55, 0.55)
            y += random.uniform(-0.55, 0.55)
            await self._dispatch_mouse_move(tab, x, y)
            await asyncio.sleep(jitter(self.profile.mouse_pause_min, self.profile.mouse_pause_max))

        self._set_cursor(tab, float(target_x), float(target_y))

    async def _random_point_in_element(self, element: Any) -> tuple[float, float]:
        position = await element.get_position()
        width = max(float(position.width), 1.0)
        height = max(float(position.height), 1.0)
        x = float(position.left) + width * random.uniform(0.28, 0.72)
        y = float(position.top) + height * random.uniform(0.28, 0.72)
        return x, y

    async def move_mouse_to_element(self, element: Any) -> tuple[float, float]:
        x, y = await self._random_point_in_element(element)
        await self.move_mouse_to(element.tab, x, y)
        return x, y

    async def _fallback_click(self, element: Any) -> None:
        try:
            await element.click()
            return
        except Exception:
            pass
        try:
            await element.apply("(el) => el.focus()")
            await element.apply("(el) => el.click()")
        except Exception:
            pass

    async def click_element(self, element: Any) -> None:
        try:
            await element.scroll_into_view()
        except Exception:
            pass

        try:
            center_x, center_y = await self.move_mouse_to_element(element)
            await async_sleep(self.profile.pre_click_pause_min, self.profile.pre_click_pause_max)
            await element.tab.mouse_click(center_x, center_y)
        except Exception:
            await async_sleep(self.profile.pre_click_pause_min, self.profile.pre_click_pause_max)
            await self._fallback_click(element)

        await async_sleep(self.profile.post_click_pause_min, self.profile.post_click_pause_max)

    async def click_element_new_tab(self, element: Any) -> None:
        try:
            await element.scroll_into_view()
        except Exception:
            pass

        try:
            x, y = await self.move_mouse_to_element(element)
            await async_sleep(self.profile.pre_click_pause_min, self.profile.pre_click_pause_max)
            await element.tab.mouse_click(x, y, modifiers=2)
        except Exception:
            await self._fallback_click(element)

        await async_sleep(self.profile.post_click_pause_min, self.profile.post_click_pause_max)

    async def type_text(self, element: Any, text: str, clear_before: bool = False) -> None:
        await element.scroll_into_view()
        await self.click_element(element)

        if clear_before:
            await element.clear_input()
            await async_sleep(0.05, 0.2)

        for char in text:
            await element.send_keys(char)
            await async_sleep(self.profile.key_delay_min, self.profile.key_delay_max)
            if random.random() <= self.profile.key_thinking_pause_chance:
                await async_sleep(self.profile.key_thinking_pause_min, self.profile.key_thinking_pause_max)

    async def press_enter(self, element: Any) -> None:
        await element.send_keys("\n")
        await async_sleep(0.08, 0.22)
