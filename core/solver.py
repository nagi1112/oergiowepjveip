from __future__ import annotations

import asyncio
import base64
import io
import math
import random
import time
from typing import Any, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .human_actions import HumanActions
from .image_processor import ImageProcessor  # ваш существующий image_processor

# Конфигурация Anti-Captcha (замените на свой ключ)
ANTICAPTCHA_KEY = "6c22ec396e7f82a01b23961d218fc207"


class CaptchaSolverNodriver:
    """
    Решатель капч для nodriver:
    - пазл-слайдер (через компьютерное зрение)
    - клик-капча (через Anti-Captcha ImageToCoordinatesTask)
    """

    def __init__(self, tab: Any, human: HumanActions, logger: Any = None):
        self.tab = tab
        self.human = human
        self.logger = logger

    async def _sleep(self, seconds: float):
        """Асинхронный сон с учётом возможного метода tab.wait"""
        try:
            await self.tab.wait(seconds)
        except Exception:
            await asyncio.sleep(seconds)

    async def _cdp_mouse(self, type_: str, x: float, y: float,
                         button: str = "left", buttons: int = 0):
        """Отправка CDP-события мыши"""
        await self.tab.send(
            "Input.dispatchMouseEvent",
            {
                "type": type_,
                "x": x,
                "y": y,
                "button": button,
                "buttons": buttons,
                "clickCount": 1,
            }
        )

    # ---------- Пазл-капча ----------

    async def _get_canvas_rect(self) -> Optional[dict]:
        """Возвращает bounding rect canvas пазла в CSS-пикселях"""
        try:
            canvas = await self.tab.select("canvas.AdvancedCaptcha-KaleidoscopeCanvas", timeout=5)
            if not canvas:
                return None
            rect = await self.tab.evaluate(
                """
                (el) => {
                    const r = el.getBoundingClientRect();
                    return {left: r.left, top: r.top, width: r.width, height: r.height};
                }
                """,
                canvas
            )
            return rect
        except Exception:
            return None

    async def _get_puzzle_image_cv2(self) -> Optional[np.ndarray]:
        """Возвращает изображение canvas в BGR (для OpenCV)"""
        rect = await self._get_canvas_rect()
        if not rect:
            return None

        # Скриншот всей страницы
        screenshot_png = await self.tab.screenshot()  # bytes
        img_full = cv2.imdecode(np.frombuffer(screenshot_png, np.uint8), cv2.IMREAD_COLOR)

        # Получаем devicePixelRatio
        dpr = await self.tab.evaluate("window.devicePixelRatio || 1", return_by_value=True)

        left = int(rect["left"] * dpr)
        top = int(rect["top"] * dpr)
        right = int((rect["left"] + rect["width"]) * dpr)
        bottom = int((rect["top"] + rect["height"]) * dpr)

        if right > img_full.shape[1] or bottom > img_full.shape[0]:
            return None
        return img_full[top:bottom, left:right]

    async def _get_slider_and_track(self) -> Tuple[Optional[Any], Optional[Any]]:
        """Возвращает элементы слайдера и трека"""
        try:
            slider = await self.tab.select("#captcha-slider", timeout=5)
            track = await self.tab.select(".CaptchaSlider .Track", timeout=5)
            return slider, track
        except Exception:
            return None, None

    async def solve_puzzle(self) -> bool:
        """Решает пазл-капчу (слайдер)"""
        if self.logger:
            self.logger.info("Пытаюсь решить пазл-капчу...")

        joints = await self._init_puzzle_joints()
        if not joints:
            if self.logger:
                self.logger.warning("Не удалось найти швы пазла")
            return False

        slider, track = await self._get_slider_and_track()
        if not slider or not track:
            return False

        # Получаем координаты
        rect_slider = await slider.rect()
        rect_track = await track.rect()

        cur_x = rect_slider["x"] + rect_slider["width"] / 2
        cur_y = rect_slider["y"] + rect_slider["height"] / 2
        track_left = rect_track["x"]
        track_width = rect_track["width"]
        y_line = cur_y

        # Нажимаем на слайдер
        await self.human.move_mouse_to(self.tab, cur_x, cur_y)
        await self._sleep(random.uniform(0.03, 0.08))
        await self._cdp_mouse("mousePressed", cur_x, cur_y, buttons=1)

        try:
            best_x = cur_x
            best_err = await self._puzzle_error(joints)

            steps = 14
            for i in range(1, steps):
                frac = i / (steps - 1)
                target_x = track_left + frac * track_width
                cur_x = await self._drag_x_human(cur_x, target_x, y_line)
                await self._sleep(random.uniform(0.05, 0.12))

                err = await self._puzzle_error(joints)
                if err < best_err:
                    best_err = err
                    best_x = cur_x

            # Возврат к лучшей позиции
            cur_x = await self._drag_x_human(cur_x, best_x, y_line)
            await self._sleep(0.2)
        finally:
            await self._cdp_mouse("mouseReleased", cur_x, y_line, buttons=0)

        # Проверяем, исчезла ли капча
        await self._sleep(1)
        return not await self._is_captcha_present()

    async def _init_puzzle_joints(self):
        img = await self._get_puzzle_image_cv2()
        if img is None:
            return None
        return ImageProcessor.get_puzzle_joints(img)

    async def _puzzle_error(self, joints) -> float:
        img = await self._get_puzzle_image_cv2()
        if img is None:
            return 1e9
        return ImageProcessor.evaluate_joints_diff(img, joints)

    async def _drag_x_human(self, cur_x: float, target_x: float, y_line: float,
                            step_px=2.0, pause_min=0.015, pause_max=0.03,
                            y_jitter=0.15) -> float:
        """Плавное перетаскивание слайдера с человеческими паузами"""
        x = cur_x
        tx = target_x
        step = max(0.2, step_px)
        if abs(x - tx) < 0.1:
            return tx

        direction = 1.0 if tx > x else -1.0
        while True:
            dist = abs(tx - x)
            if dist <= step:
                x = tx
            else:
                x += direction * step

            yy = y_line + (random.uniform(-y_jitter, y_jitter) if y_jitter else 0.0)
            await self._cdp_mouse("mouseMoved", x, yy, buttons=1)
            await asyncio.sleep(random.uniform(pause_min, pause_max))

            if x == tx:
                return x

    # ---------- Клик-капча ----------

    async def _get_captcha_center_rect(self) -> Optional[dict]:
        """
        Возвращает bounding box центральной области, где обычно находится клик-капча.
        Коэффициенты подобраны под Яндекс (0.348, 0.492).
        """
        try:
            viewport = await self.tab.evaluate(
                "({w: window.innerWidth, h: window.innerHeight})",
                return_by_value=True
            )
            w, h = viewport["w"], viewport["h"]
            crop_w = int(w * 0.3484375)
            crop_h = int(h * 0.49237805)
            left = (w - crop_w) // 2
            top = (h - crop_h) // 2
            return {"left": left, "top": top, "width": crop_w, "height": crop_h}
        except Exception:
            return None

    async def _screenshot_crop_center(self) -> Optional[bytes]:
        """Скриншот центральной области и возврат PNG-байтов"""
        rect = await self._get_captcha_center_rect()
        if not rect:
            return None

        full_png = await self.tab.screenshot()
        full = Image.open(io.BytesIO(full_png)).convert("RGB")
        cropped = full.crop((rect["left"], rect["top"],
                             rect["left"] + rect["width"],
                             rect["top"] + rect["height"]))
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()

    async def solve_click_captcha(self) -> bool:
        """Решает клик-капчу через Anti-Captcha"""
        if self.logger:
            self.logger.info("Пытаюсь решить клик-капчу через Anti-Captcha...")

        # Проверяем, точно ли это клик-капча
        html = await self.tab.get_content()
        if "Нажмите в таком порядке:" not in html:
            return False

        # Получаем скриншот области
        crop_bytes = await self._screenshot_crop_center()
        if not crop_bytes:
            return False

        # Отправляем в Anti-Captcha
        task_id = await self._upload_to_anticaptcha(crop_bytes)
        if not task_id:
            return False

        coords = await self._get_anticaptcha_result(task_id)
        if not coords:
            return False

        # Конвертируем координаты из изображения в CSS-координаты окна
        rect = await self._get_captcha_center_rect()
        if not rect:
            return False

        dpr = await self.tab.evaluate("window.devicePixelRatio || 1", return_by_value=True)

        for (x_img, y_img) in coords:
            # Пересчёт: из пикселей кропа в CSS-пиксели экрана
            css_x = rect["left"] + x_img  # / dpr? В кропе координаты уже в пикселях скриншота, которые соответствуют CSS при dpr=1
            css_y = rect["top"] + y_img
            # Но из-за dpr скриншот имеет больше пикселей, поэтому координаты в кропе уже умножены на dpr.
            # Нужно разделить на dpr, чтобы получить CSS-координаты для клика.
            css_x /= dpr
            css_y /= dpr

            # Двигаем мышь human-like и кликаем
            await self.human.move_mouse_to(self.tab, css_x, css_y)
            await self._sleep(random.uniform(0.02, 0.05))
            await self.tab.mouse_click(css_x, css_y)

        # Нажимаем кнопку подтверждения
        await self._click_submit_button()
        await self._sleep(1)

        return not await self._is_captcha_present()

    async def _upload_to_anticaptcha(self, image_bytes: bytes) -> Optional[int]:
        """Загружает изображение в Anti-Captcha и возвращает taskId"""
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        import requests
        resp = requests.post(
            "https://api.anti-captcha.com/createTask",
            json={
                "clientKey": ANTICAPTCHA_KEY,
                "task": {
                    "type": "ImageToCoordinatesTask",
                    "body": b64,
                    "comment": "Select objects in specified order",
                }
            },
            timeout=30
        )
        data = resp.json()
        return data.get("taskId")

    async def _get_anticaptcha_result(self, task_id: int, attempts=60, delay=5) -> Optional[list]:
        """Получает результат от Anti-Captcha (список координат [x,y])"""
        import requests
        for _ in range(attempts):
            resp = requests.post(
                "https://api.anti-captcha.com/getTaskResult",
                json={"clientKey": ANTICAPTCHA_KEY, "taskId": task_id},
                timeout=30
            )
            data = resp.json()
            if data.get("status") == "ready":
                sol = data.get("solution", {})
                coords = sol.get("coordinates")
                if coords:
                    return [[p["x"], p["y"]] for p in coords]
                return None
            await asyncio.sleep(delay)
        return None

    async def _click_submit_button(self):
        """Нажимает кнопку подтверждения капчи"""
        try:
            btn = await self.tab.select("button[data-testid='submit']", timeout=3)
            if btn:
                await self.human.click_element(btn)
                return
        except Exception:
            pass
        # Фолбэк: CDP-клик по центру кнопки
        try:
            rect = await self.tab.evaluate(
                """
                (() => {
                    const btn = document.querySelector('button[data-testid="submit"]');
                    if (!btn) return null;
                    const r = btn.getBoundingClientRect();
                    return {x: r.left + r.width/2, y: r.top + r.height/2};
                })()
                """,
                return_by_value=True
            )
            if rect:
                await self.human.move_mouse_to(self.tab, rect["x"], rect["y"])
                await self.tab.mouse_click(rect["x"], rect["y"])
        except Exception:
            pass

    # ---------- Общий метод ----------

    async def _is_captcha_present(self) -> bool:
        """Проверяет наличие любой капчи на странице"""
        html = await self.tab.get_content()
        return any(marker in html for marker in [
            "Подтвердите, что запросы отправляли вы, а не робот",
            "Перемещайте слайдер",
            "Нажмите в таком порядке:",
            'data-testid="submit"'
        ])

    async def solve_smart(self, max_attempts=3) -> bool:
        """
        Умный решатель: определяет тип капчи и пытается решить.
        Возвращает True, если капча успешно пройдена.
        """
        for attempt in range(max_attempts):
            html = await self.tab.get_content()
            if "Нажмите в таком порядке:" in html:
                if await self.solve_click_captcha():
                    return True
            elif "Перемещайте слайдер" in html or "captcha-slider" in html:
                if await self.solve_puzzle():
                    return True
            elif "Подтвердите, что запросы отправляли вы" in html:
                # Просто ждём кнопку "Я не робот" – она может быть в iframe
                if await self._click_confirm_button():
                    return True
            else:
                # Капчи нет
                return True

            await self._sleep(2)

        return False

    async def _click_confirm_button(self) -> bool:
        """Пытается нажать кнопку 'Я не робот' (обычно в iframe)"""
        try:
            # Ищем iframe с капчей
            frames = await self.tab.select_all("iframe")
            for frame in frames:
                # Переключиться на frame через CDP? В nodriver нет прямого switch_to.
                # Альтернатива: найти элемент #js-button внутри страницы (он может быть в корне)
                try:
                    btn = await self.tab.select("#js-button", timeout=2)
                    if btn:
                        await self.human.click_element(btn)
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False