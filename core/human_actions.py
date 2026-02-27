from __future__ import annotations

import asyncio
import importlib
import random
from dataclasses import dataclass
from typing import Any, Optional

from .utils import async_sleep, jitter


@dataclass(slots=True)
class HumanProfile:
    mouse_steps_min: int = 14
    mouse_steps_max: int = 30
    mouse_pause_min: float = 0.002
    mouse_pause_max: float = 0.012
    pre_click_pause_min: float = 0.03
    pre_click_pause_max: float = 0.10
    post_click_pause_min: float = 0.05
    post_click_pause_max: float = 0.18
    key_delay_min: float = 0.03
    key_delay_max: float = 0.09
    key_thinking_pause_chance: float = 0.12
    key_thinking_pause_min: float = 0.15
    key_thinking_pause_max: float = 0.45
    mouse_visual_debug: bool = False
    mouse_visual_debug_ttl_seconds: float = 2.5
    mouse_visual_debug_step_min: int = 60
    mouse_visual_debug_pause_min: float = 0.015
    mouse_visual_debug_pause_max: float = 0.035


class HumanActions:
    def __init__(self, profile: Optional[HumanProfile] = None, logger: Any = None) -> None:
        self.profile = profile or HumanProfile()
        self.logger = logger
        self._cursor_position: tuple[float, float] = (0.0, 0.0)

    def _log(self, message: str, *args: Any) -> None:
        if self.logger is None:
            return
        try:
            self.logger.info(message, *args)
        except Exception:
            pass

    def _tab_key(self, tab: Any) -> int:
        return id(tab)

    def _nodriver(self) -> Any:
        return importlib.import_module("nodriver")

    def _get_cursor(self, tab: Any) -> tuple[float, float]:
        return self._cursor_position

    def _set_cursor(self, tab: Any, x: float, y: float) -> None:
        self._cursor_position = (x, y)

    async def _dispatch_mouse_move(self, tab: Any, x: float, y: float) -> None:
        nodriver = self._nodriver()
        await tab.send(nodriver.cdp.input_.dispatch_mouse_event("mouseMoved", x=float(x), y=float(y)))

    async def _debug_draw_mouse_path(self, tab: Any, x: float, y: float, reset: bool = False) -> None:
        if not self.profile.mouse_visual_debug:
            return

        script = """
        (payload) => {
          const ensure = () => {
            if (window.__humanMouseDebug) {
              return window.__humanMouseDebug;
            }

            const canvas = document.createElement('canvas');
            canvas.id = '__human_mouse_debug_canvas';
            canvas.style.position = 'fixed';
            canvas.style.left = '0';
            canvas.style.top = '0';
            canvas.style.width = '100vw';
            canvas.style.height = '100vh';
            canvas.style.pointerEvents = 'none';
            canvas.style.zIndex = '2147483647';
            document.documentElement.appendChild(canvas);

                        const state = {
              canvas,
              ctx: canvas.getContext('2d'),
                            points: []
            };

                        const marker = document.createElement('div');
                        marker.id = '__human_mouse_debug_marker';
                        marker.style.position = 'fixed';
                        marker.style.left = '0px';
                        marker.style.top = '0px';
                        marker.style.width = '16px';
                        marker.style.height = '16px';
                        marker.style.marginLeft = '-8px';
                        marker.style.marginTop = '-8px';
                        marker.style.border = '2px solid rgba(0, 120, 255, 1)';
                        marker.style.background = 'rgba(80, 180, 255, 0.35)';
                        marker.style.borderRadius = '50%';
                        marker.style.pointerEvents = 'none';
                        marker.style.zIndex = '2147483647';
                        marker.style.boxShadow = '0 0 12px rgba(0, 120, 255, 0.95)';
                        document.documentElement.appendChild(marker);
                        state.marker = marker;

            const resize = () => {
              const dpr = window.devicePixelRatio || 1;
              const w = Math.max(window.innerWidth, 1);
              const h = Math.max(window.innerHeight, 1);
              canvas.width = Math.floor(w * dpr);
              canvas.height = Math.floor(h * dpr);
              canvas.style.width = `${w}px`;
              canvas.style.height = `${h}px`;
              state.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            };

            resize();
            window.addEventListener('resize', resize, { passive: true });
            window.__humanMouseDebug = state;
            return state;
          };

          const state = ensure();
                    if (payload.reset) {
            state.points = [];
          }

                    state.points.push({ x: payload.x, y: payload.y, ts: Date.now() });
                    const cutoff = Date.now() - payload.ttlMs;
                    state.points = state.points.filter((point) => point.ts >= cutoff);
          const ctx = state.ctx;
          const w = Math.max(window.innerWidth, 1);
          const h = Math.max(window.innerHeight, 1);
          ctx.clearRect(0, 0, w, h);

          if (state.points.length > 1) {
            ctx.beginPath();
            ctx.moveTo(state.points[0].x, state.points[0].y);
            for (let i = 1; i < state.points.length; i += 1) {
              ctx.lineTo(state.points[i].x, state.points[i].y);
            }
                        ctx.strokeStyle = 'rgba(40, 170, 255, 0.98)';
                        ctx.lineWidth = 4;
                        ctx.lineCap = 'round';
                        ctx.lineJoin = 'round';
                        ctx.shadowColor = 'rgba(40, 170, 255, 0.9)';
                        ctx.shadowBlur = 12;
            ctx.stroke();
                        ctx.shadowBlur = 0;

                        for (let i = 0; i < state.points.length; i += 1) {
                            const point = state.points[i];
                            ctx.beginPath();
                            ctx.arc(point.x, point.y, 1.8, 0, Math.PI * 2);
                            ctx.fillStyle = 'rgba(120, 210, 255, 0.95)';
                            ctx.fill();
                        }
          }

          const p = state.points[state.points.length - 1];
          if (p) {
                        if (state.marker) {
                            state.marker.style.left = `${p.x}px`;
                            state.marker.style.top = `${p.y}px`;
                        }

                        ctx.beginPath();
                        ctx.arc(p.x, p.y, 12, 0, Math.PI * 2);
                        ctx.fillStyle = 'rgba(40, 170, 255, 0.18)';
                        ctx.fill();

            ctx.beginPath();
                        ctx.arc(p.x, p.y, 7, 0, Math.PI * 2);
                        ctx.fillStyle = 'rgba(15, 130, 255, 1)';
            ctx.fill();

                        ctx.beginPath();
                        ctx.arc(p.x, p.y, 2.2, 0, Math.PI * 2);
                        ctx.fillStyle = 'rgba(255, 255, 255, 1)';
                        ctx.fill();
          }
        }
        """
        ttl_ms = max(1000, int(self.profile.mouse_visual_debug_ttl_seconds * 1000))
        await tab.evaluate(script, {"x": float(x), "y": float(y), "reset": bool(reset), "ttlMs": ttl_ms})

        async def _debug_show_path_snapshot(self, tab: Any, points: list[tuple[float, float]], hold_seconds: float) -> None:
                if not self.profile.mouse_visual_debug or not points:
                        return

                script = """
                (payload) => {
                    const ensure = () => {
                        if (window.__humanMouseDebug) {
                            return window.__humanMouseDebug;
                        }
                        const canvas = document.createElement('canvas');
                        canvas.id = '__human_mouse_debug_canvas';
                        canvas.style.position = 'fixed';
                        canvas.style.left = '0';
                        canvas.style.top = '0';
                        canvas.style.width = '100vw';
                        canvas.style.height = '100vh';
                        canvas.style.pointerEvents = 'none';
                        canvas.style.zIndex = '2147483647';
                        document.documentElement.appendChild(canvas);

                        const state = {
                            canvas,
                            ctx: canvas.getContext('2d'),
                            points: []
                        };

                        const marker = document.createElement('div');
                        marker.id = '__human_mouse_debug_marker';
                        marker.style.position = 'fixed';
                        marker.style.left = '0px';
                        marker.style.top = '0px';
                        marker.style.width = '16px';
                        marker.style.height = '16px';
                        marker.style.marginLeft = '-8px';
                        marker.style.marginTop = '-8px';
                        marker.style.border = '2px solid rgba(0, 120, 255, 1)';
                        marker.style.background = 'rgba(80, 180, 255, 0.35)';
                        marker.style.borderRadius = '50%';
                        marker.style.pointerEvents = 'none';
                        marker.style.zIndex = '2147483647';
                        marker.style.boxShadow = '0 0 12px rgba(0, 120, 255, 0.95)';
                        document.documentElement.appendChild(marker);
                        state.marker = marker;

                        const resize = () => {
                            const dpr = window.devicePixelRatio || 1;
                            const w = Math.max(window.innerWidth, 1);
                            const h = Math.max(window.innerHeight, 1);
                            canvas.width = Math.floor(w * dpr);
                            canvas.height = Math.floor(h * dpr);
                            canvas.style.width = `${w}px`;
                            canvas.style.height = `${h}px`;
                            state.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
                        };
                        resize();
                        window.addEventListener('resize', resize, { passive: true });
                        window.__humanMouseDebug = state;
                        return state;
                    };

                    const state = ensure();
                    state.points = payload.points || [];
                    const ctx = state.ctx;
                    const w = Math.max(window.innerWidth, 1);
                    const h = Math.max(window.innerHeight, 1);
                    ctx.clearRect(0, 0, w, h);

                    if (state.points.length > 1) {
                        ctx.beginPath();
                        ctx.moveTo(state.points[0].x, state.points[0].y);
                        for (let i = 1; i < state.points.length; i += 1) {
                            ctx.lineTo(state.points[i].x, state.points[i].y);
                        }
                        ctx.strokeStyle = 'rgba(40, 170, 255, 0.98)';
                        ctx.lineWidth = 4;
                        ctx.lineCap = 'round';
                        ctx.lineJoin = 'round';
                        ctx.shadowColor = 'rgba(40, 170, 255, 0.9)';
                        ctx.shadowBlur = 12;
                        ctx.stroke();
                        ctx.shadowBlur = 0;
                    }

                    const p = state.points[state.points.length - 1];
                    if (p) {
                        if (state.marker) {
                            state.marker.style.left = `${p.x}px`;
                            state.marker.style.top = `${p.y}px`;
                        }
                    }

                    if (window.__humanMouseDebugClearTimer) {
                        clearTimeout(window.__humanMouseDebugClearTimer);
                    }
                    window.__humanMouseDebugClearTimer = setTimeout(() => {
                        try {
                            const s = window.__humanMouseDebug;
                            if (!s) return;
                            const ww = Math.max(window.innerWidth, 1);
                            const hh = Math.max(window.innerHeight, 1);
                            s.ctx.clearRect(0, 0, ww, hh);
                            s.points = [];
                        } catch (e) {}
                    }, payload.holdMs);
                }
                """
                payload_points = [{"x": float(px), "y": float(py)} for px, py in points]
                await tab.evaluate(script, {"points": payload_points, "holdMs": int(max(2000, hold_seconds * 1000))})

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
        if start_x == 0.0 and start_y == 0.0:
            try:
                viewport = await tab.evaluate(
                    "({w: Math.max(window.innerWidth, 1), h: Math.max(window.innerHeight, 1)})",
                    return_by_value=True,
                )
                width = float((viewport or {}).get("w", 1200))
                height = float((viewport or {}).get("h", 800))
                start_x = width * random.uniform(0.45, 0.55)
                start_y = height * random.uniform(0.45, 0.55)
                self._set_cursor(tab, start_x, start_y)
            except Exception:
                pass
        step_count = steps or random.randint(self.profile.mouse_steps_min, self.profile.mouse_steps_max)
        pause_min = self.profile.mouse_pause_min
        pause_max = self.profile.mouse_pause_max

        if self.profile.mouse_visual_debug:
            step_count = max(step_count, self.profile.mouse_visual_debug_step_min)
            pause_min = max(pause_min, self.profile.mouse_visual_debug_pause_min)
            pause_max = max(pause_max, self.profile.mouse_visual_debug_pause_max)

        step_count = max(1, step_count)

        p0 = (float(start_x), float(start_y))
        p3 = (float(target_x), float(target_y))
        p1, p2 = self._control_points(p0, p3)
        path_points: list[tuple[float, float]] = [(p0[0], p0[1])]

        self._log(
            "Движение мыши: старт=(%.1f, %.1f) цель=(%.1f, %.1f) шагов=%s",
            p0[0],
            p0[1],
            p3[0],
            p3[1],
            step_count,
        )

        await self._debug_draw_mouse_path(tab, p0[0], p0[1], reset=True)

        for step in range(1, step_count + 1):
            t = step / step_count
            x, y = self._bezier_point(t, p0, p1, p2, p3)
            x += random.uniform(-0.55, 0.55)
            y += random.uniform(-0.55, 0.55)
            path_points.append((x, y))
            await self._dispatch_mouse_move(tab, x, y)
            await self._debug_draw_mouse_path(tab, x, y)
            if self.profile.mouse_visual_debug and (step == 1 or step == step_count or step % 10 == 0):
                self._log("Движение мыши: шаг %s/%s -> (%.1f, %.1f)", step, step_count, x, y)
            await asyncio.sleep(jitter(pause_min, pause_max))

        self._set_cursor(tab, float(target_x), float(target_y))
        self._log("Движение мыши завершено: позиция=(%.1f, %.1f)", float(target_x), float(target_y))
        if self.profile.mouse_visual_debug:
            hold_seconds = random.uniform(1.0, 1.5)
            self._log("Показываю траекторию после движения %.1f сек", hold_seconds)
            await self._debug_show_path_snapshot(tab, path_points, hold_seconds)

    async def _random_point_in_element(self, element: Any) -> tuple[float, float]:
        position = await element.get_position()
        width = max(float(position.width), 1.0)
        height = max(float(position.height), 1.0)
        x = float(position.left) + width * random.uniform(0.28, 0.72)
        y = float(position.top) + height * random.uniform(0.28, 0.72)
        return x, y

    async def move_mouse_to_element(self, element: Any) -> tuple[float, float]:
        if self.profile.mouse_visual_debug:
            try:
                await element.tab.bring_to_front()
                await element.tab.wait(0.2)
            except Exception:
                pass
        x, y = await self._random_point_in_element(element)
        self._log("Цель движения по элементу: (%.1f, %.1f)", x, y)
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
            self._log("Клик мышью: координаты=(%.1f, %.1f)", center_x, center_y)
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
            self._log("Ctrl+клик мышью: координаты=(%.1f, %.1f)", x, y)
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