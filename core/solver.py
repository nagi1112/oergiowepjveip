from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import io
import importlib
import os
import random
import tempfile
from typing import Any, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .captcha import has_captcha
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
        self._last_confirm_click_ts = 0.0
        self._confirm_click_cooldown = 12.0

    async def _sleep(self, seconds: float):
        """Асинхронный сон с учётом возможного метода tab.wait"""
        try:
            await self.tab.wait(seconds)
        except Exception:
            await asyncio.sleep(seconds)

    def _log(self, message: str, *args: Any) -> None:
        if self.logger is None:
            return
        try:
            self.logger.info(message, *args)
        except Exception:
            pass

    async def _cdp_mouse(self, type_: str, x: float, y: float,
                         button: str = "left", buttons: int = 0):
        """Отправка CDP-события мыши"""
        nodriver = importlib.import_module("nodriver")
        await self.tab.send(
            nodriver.cdp.input_.dispatch_mouse_event(
                type_,
                x=float(x),
                y=float(y),
                button=button,
                buttons=int(buttons),
                click_count=1,
            )
        )

    async def _take_screenshot_png(self) -> Optional[bytes]:
        """Снимает PNG-скриншот текущей страницы, совместимо с разными версиями nodriver."""
        # 1) Прямой метод tab.screenshot (если поддерживается)
        screenshot_method = getattr(self.tab, "screenshot", None)
        if callable(screenshot_method):
            try:
                maybe_data = screenshot_method()
                data = await maybe_data if inspect.isawaitable(maybe_data) else maybe_data
                if isinstance(data, (bytes, bytearray)) and data:
                    return bytes(data)
            except Exception as exc:
                self._log("Скриншот через tab.screenshot не удался: %s", exc)

        # 2) Метод tab.save_screenshot (актуален для части версий nodriver)
        save_screenshot_method = getattr(self.tab, "save_screenshot", None)
        if callable(save_screenshot_method):
            tmp_path = None
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="nd_cap_")
                os.close(fd)
                maybe_path = save_screenshot_method(filename=tmp_path, format="png", full_page=False)
                saved_path = await maybe_path if inspect.isawaitable(maybe_path) else maybe_path
                target_path = str(saved_path) if isinstance(saved_path, str) and saved_path else tmp_path
                with open(target_path, "rb") as fh:
                    data = fh.read()
                if data:
                    return data
            except Exception as exc:
                self._log("Скриншот через tab.save_screenshot не удался: %s", exc)
            finally:
                for path in (tmp_path,):
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass

        # 3) CDP fallback: Page.captureScreenshot
        try:
            nodriver = importlib.import_module("nodriver")
            page_domain = getattr(getattr(nodriver, "cdp", None), "page", None)
            if page_domain is not None:
                for fn_name in ("capture_screenshot", "captureScreenshot"):
                    builder = getattr(page_domain, fn_name, None)
                    if not callable(builder):
                        continue

                    for kwargs in ({"format_": "png"}, {"format": "png"}, {}):
                        try:
                            command = builder(**kwargs)
                        except TypeError:
                            continue

                        try:
                            result = await self.tab.send(command)
                        except Exception:
                            continue

                        if isinstance(result, (bytes, bytearray)) and result:
                            return bytes(result)

                        if isinstance(result, str) and result:
                            try:
                                return base64.b64decode(result)
                            except (binascii.Error, ValueError):
                                continue

                        payload = result if isinstance(result, dict) else getattr(result, "__dict__", {})
                        data_b64 = payload.get("data") if isinstance(payload, dict) else None
                        if isinstance(data_b64, str) and data_b64:
                            try:
                                return base64.b64decode(data_b64)
                            except Exception:
                                continue
        except Exception as exc:
            self._log("Скриншот через CDP fallback не удался: %s", exc)

        self._log("Не удалось получить скриншот: нет поддерживаемого API в текущем Tab")
        return None

    # ---------- Пазл-капча ----------

    async def _get_canvas_rect(self) -> Optional[dict]:
        """Возвращает bounding rect canvas пазла в CSS-пикселях"""
        try:
            canvas = await self.tab.select("canvas.AdvancedCaptcha-KaleidoscopeCanvas", timeout=5)
            if not canvas:
                return None
            position = await canvas.get_position()
            return {
                "left": float(position.left),
                "top": float(position.top),
                "width": float(position.width),
                "height": float(position.height),
            }
        except Exception:
            return None

    async def _get_puzzle_image_cv2(self) -> Optional[np.ndarray]:
        """Возвращает изображение canvas в BGR (для OpenCV)"""
        rect = await self._get_canvas_rect()
        if not rect:
            return None

        # Скриншот всей страницы
        screenshot_png = await self._take_screenshot_png()
        if not screenshot_png:
            return None
        img_full = cv2.imdecode(np.frombuffer(screenshot_png, np.uint8), cv2.IMREAD_COLOR)

        # Получаем devicePixelRatio
        dpr = float(await self.tab.evaluate("window.devicePixelRatio || 1", return_by_value=True) or 1.0)

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
        rect_slider = await slider.get_position()
        rect_track = await track.get_position()

        cur_x = float(rect_slider.left) + float(rect_slider.width) / 2
        cur_y = float(rect_slider.top) + float(rect_slider.height) / 2
        track_left = float(rect_track.left)
        track_width = float(rect_track.width)
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
        for attempt in range(1, 4):
            try:
                full_png = await self._take_screenshot_png()
                if not full_png:
                    self._log("Кроп капчи: пустой скриншот (attempt %s/3)", attempt)
                    await self._sleep(0.4)
                    continue

                full = Image.open(io.BytesIO(full_png)).convert("RGB")
                img_w, img_h = full.size

                try:
                    dpr_val = await self.tab.evaluate("window.devicePixelRatio || 1", return_by_value=True)
                    dpr = float(dpr_val or 1.0)
                except Exception:
                    dpr = 1.0

                rect = await self._get_captcha_center_rect()
                if rect:
                    left = int(float(rect["left"]) * dpr)
                    top = int(float(rect["top"]) * dpr)
                    crop_w = int(float(rect["width"]) * dpr)
                    crop_h = int(float(rect["height"]) * dpr)
                else:
                    self._log("Кроп капчи: не удалось получить viewport-rect, беру центр от размеров скриншота")
                    crop_w = int(img_w * 0.3484375)
                    crop_h = int(img_h * 0.49237805)
                    left = (img_w - crop_w) // 2
                    top = (img_h - crop_h) // 2

                left = max(0, min(left, img_w - 1))
                top = max(0, min(top, img_h - 1))
                right = max(left + 1, min(left + crop_w, img_w))
                bottom = max(top + 1, min(top + crop_h, img_h))

                if right <= left or bottom <= top:
                    self._log(
                        "Кроп капчи: некорректные границы left=%s top=%s right=%s bottom=%s img=%sx%s (attempt %s/3)",
                        left,
                        top,
                        right,
                        bottom,
                        img_w,
                        img_h,
                        attempt,
                    )
                    await self._sleep(0.4)
                    continue

                cropped = full.crop((left, top, right, bottom))
                buf = io.BytesIO()
                cropped.save(buf, format="PNG")
                data = buf.getvalue()
                if data:
                    self._log(
                        "Кроп капчи: успешно, размер=%s байт, область=(%s,%s)-(%s,%s), dpr=%.2f",
                        len(data),
                        left,
                        top,
                        right,
                        bottom,
                        dpr,
                    )
                    return data

                self._log("Кроп капчи: пустой результат после crop (attempt %s/3)", attempt)
            except Exception as exc:
                self._log("Кроп капчи exception (attempt %s/3): %s", attempt, exc)

            await self._sleep(0.4)

        return None

    async def solve_click_captcha(self) -> bool:
        """Решает клик-капчу через Anti-Captcha"""
        self._log("Пытаюсь решить клик-капчу через Anti-Captcha...")

        if not await self._wait_click_captcha_prompt(timeout=10.0, step=0.7):
            self._log("Клик-капча не подтверждена по HTML-маркеру, пропускаю Anti-Captcha")
            return False

        # Получаем скриншот области
        crop_bytes = await self._screenshot_crop_center()
        if not crop_bytes:
            self._log("Не удалось получить скриншот центральной области капчи")
            return False
        self._log("Скриншот для Anti-Captcha получен, размер=%s байт", len(crop_bytes))

        # Отправляем в Anti-Captcha
        task_id = await self._upload_to_anticaptcha(crop_bytes)
        if not task_id:
            self._log("Anti-Captcha: task_id не получен")
            return False

        self._log("Anti-Captcha: создана задача task_id=%s", task_id)

        coords = await self._get_anticaptcha_result(task_id)
        if not coords:
            self._log("Anti-Captcha: координаты не получены")
            return False

        self._log("Anti-Captcha: получено координат=%s", len(coords))

        # Конвертируем координаты из изображения в CSS-координаты окна
        rect = await self._get_captcha_center_rect()
        if not rect:
            self._log("Не удалось получить rect центральной области для пересчёта координат")
            return False

        dpr = float(await self.tab.evaluate("window.devicePixelRatio || 1", return_by_value=True) or 1.0)
        if dpr <= 0:
            dpr = 1.0

        for (x_img, y_img) in coords:
            # Пересчёт: из пикселей кропа в CSS-пиксели экрана
            css_x = float(rect["left"]) + (float(x_img) / dpr)
            css_y = float(rect["top"]) + (float(y_img) / dpr)

            self._log(
                "Координата капчи: img=(%s,%s) -> css=(%.1f,%.1f), dpr=%.2f",
                x_img,
                y_img,
                css_x,
                css_y,
                float(dpr),
            )

            # Двигаем мышь human-like и кликаем
            await self.human.move_mouse_to(self.tab, css_x, css_y)
            await self._sleep(random.uniform(0.02, 0.05))
            await self.tab.mouse_click(css_x, css_y)

        # Нажимаем кнопку подтверждения
        await self._click_submit_button()
        await self._sleep(1)

        solved = not await self._is_captcha_present()
        self._log("Результат клик-капчи: %s", "успех" if solved else "неуспех")
        return solved

    async def _upload_to_anticaptcha(self, image_bytes: bytes) -> Optional[int]:
        """Загружает изображение в Anti-Captcha и возвращает taskId"""
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        import requests

        payload = {
            "clientKey": ANTICAPTCHA_KEY,
            "task": {
                "type": "ImageToCoordinatesTask",
                "body": b64,
                "comment": "Select objects in specified order",
            },
        }

        for attempt in range(1, 4):
            try:
                self._log("Anti-Captcha createTask: попытка %s/3", attempt)
                resp = await asyncio.to_thread(
                    requests.post,
                    "https://api.anti-captcha.com/createTask",
                    json=payload,
                    timeout=30,
                )
                data = resp.json()
                if data.get("errorId"):
                    self._log("Anti-Captcha createTask error: %s", data)
                    return None
                task_id = data.get("taskId")
                if task_id:
                    return int(task_id)
                self._log("Anti-Captcha createTask: пустой taskId, ответ=%s", data)
            except Exception as exc:
                self._log("Anti-Captcha createTask exception (attempt %s/3): %s", attempt, exc)
            await asyncio.sleep(1.0)
        return None

    async def _get_anticaptcha_result(self, task_id: int, attempts=60, delay=5) -> Optional[list]:
        """Получает результат от Anti-Captcha (список координат [x,y])"""
        import requests
        for poll in range(1, attempts + 1):
            try:
                resp = await asyncio.to_thread(
                    requests.post,
                    "https://api.anti-captcha.com/getTaskResult",
                    json={"clientKey": ANTICAPTCHA_KEY, "taskId": task_id},
                    timeout=30,
                )
                data = resp.json()
            except Exception as exc:
                self._log("Anti-Captcha getTaskResult exception (poll %s/%s): %s", poll, attempts, exc)
                await asyncio.sleep(delay)
                continue

            if data.get("errorId"):
                self._log("Anti-Captcha getTaskResult error: %s", data)
                return None

            status = data.get("status")
            if status == "ready":
                sol = data.get("solution", {})
                coords = sol.get("coordinates")
                if coords:
                    return [[p["x"], p["y"]] for p in coords]
                self._log("Anti-Captcha ready без coordinates: %s", data)
                return None

            if poll == 1 or poll % 3 == 0:
                self._log("Anti-Captcha task %s: status=%s (poll %s/%s)", task_id, status, poll, attempts)
            await asyncio.sleep(delay)
        return None

    async def _click_submit_button(self):
        """Нажимает кнопку подтверждения капчи"""
        selectors = [
            "button[data-testid='submit']",
            "button[type='submit']",
            "button.AdvancedCaptcha-Button",
            "button.Button2[role='button']",
        ]
        for selector in selectors:
            try:
                btn = await self.tab.select(selector, timeout=2)
                if btn:
                    self._log("Нажимаю submit по селектору: %s", selector)
                    await self.human.click_element(btn)
                    return
            except Exception:
                pass

        # Фолбэк: CDP-клик по центру кнопки
        try:
            rect = await self.tab.evaluate(
                """
                (() => {
                    const btn =
                      document.querySelector('button[data-testid="submit"]') ||
                      document.querySelector('button[type="submit"]') ||
                      Array.from(document.querySelectorAll('button')).find((b) => {
                        const t = (b.textContent || '').toLowerCase();
                        return t.includes('подтверд') || t.includes('далее') || t.includes('submit');
                      });
                    if (!btn) return null;
                    const r = btn.getBoundingClientRect();
                    return {x: r.left + r.width/2, y: r.top + r.height/2};
                })()
                """,
                return_by_value=True
            )
            if rect:
                self._log("Нажимаю submit через координатный fallback")
                await self.human.move_mouse_to(self.tab, rect["x"], rect["y"])
                await self.tab.mouse_click(rect["x"], rect["y"])
        except Exception:
            pass

    async def _wait_click_captcha_prompt(self, timeout: float = 10.0, step: float = 0.7) -> bool:
        loop = asyncio.get_running_loop()
        started = loop.time()
        while loop.time() - started < timeout:
            try:
                html = (await self.tab.get_content()).lower()
            except Exception:
                html = ""

            if "нажмите в таком порядке" in html:
                return True

            if not await self._is_captcha_present():
                return False

            await self._sleep(step)
        return False

    async def _captcha_kind(self) -> str:
        try:
            html = (await self.tab.get_content()).lower()
        except Exception:
            html = ""

        if "нажмите в таком порядке" in html:
            return "click"
        if "перемещайте слайдер" in html or "captcha-slider" in html:
            return "slider"
        if "подтвердите, что запросы отправляли вы" in html or "js-button" in html:
            return "confirm"
        return "none"

    async def _wait_after_confirm_click(self, timeout: float = 12.0, step: float = 0.8) -> str:
        loop = asyncio.get_running_loop()
        started = loop.time()
        last_kind = "confirm"

        while loop.time() - started < timeout:
            kind = await self._captcha_kind()
            last_kind = kind
            if kind != "confirm":
                return kind
            await self._sleep(step)

        return last_kind

    # ---------- Общий метод ----------

    async def _is_captcha_present(self) -> bool:
        """Проверяет наличие любой капчи на странице"""
        try:
            return bool(await has_captcha(self.tab))
        except Exception:
            return False

    async def solve_smart(self, max_attempts=3) -> bool:
        """
        Умный решатель: определяет тип капчи и пытается решить.
        Возвращает True, если капча успешно пройдена.
        """
        for attempt in range(1, max_attempts + 1):
            kind = await self._captcha_kind()
            self._log("Captcha attempt %s/%s, тип=%s", attempt, max_attempts, kind)

            if kind == "none":
                return True
            if kind == "click":
                if await self.solve_click_captcha():
                    return True
            elif kind == "slider":
                if await self.solve_puzzle():
                    return True
            elif kind == "confirm":
                now = asyncio.get_running_loop().time()
                cooldown_left = self._confirm_click_cooldown - (now - self._last_confirm_click_ts)

                if cooldown_left > 0:
                    self._log("Confirm в cooldown: жду %.1f сек перед повторным кликом", cooldown_left)
                    await self._sleep(min(cooldown_left, 1.2))
                    continue

                clicked = await self._click_confirm_button()
                if not clicked:
                    self._log("Confirm-кнопка не найдена/не кликнулась на этой попытке")
                    await self._sleep(1.0)
                    continue

                self._last_confirm_click_ts = asyncio.get_running_loop().time()
                next_kind = await self._wait_after_confirm_click(timeout=12.0, step=0.8)

                if next_kind == "none":
                    return True
                if next_kind == "click":
                    if await self.solve_click_captcha():
                        return True
                    await self._sleep(1.0)
                    continue
                if next_kind == "slider":
                    if await self.solve_puzzle():
                        return True
                    await self._sleep(1.0)
                    continue

                self._log("Confirm остался активным после ожидания перехода")

            await self._sleep(2)

        return False

    async def _click_confirm_button(self) -> bool:
        """Пытается нажать кнопку 'Я не робот' (обычно в iframe)"""
        try:
            js_clicked = await self.tab.evaluate(
                """
                (() => {
                    const candidates = [
                        document.querySelector('#js-button'),
                        document.querySelector('button[data-testid="submit"]'),
                        document.querySelector('button[type="submit"]'),
                        ...Array.from(document.querySelectorAll('button')).filter((b) => {
                            const t = (b.textContent || '').toLowerCase();
                            return t.includes('я не робот') || t.includes('подтверд') || t.includes('continue');
                        })
                    ].filter(Boolean);
                    if (!candidates.length) return false;
                    candidates[0].click();
                    return true;
                })()
                """,
                return_by_value=True,
            )
            if bool(js_clicked):
                self._log("Клик по confirm выполнен через JS")
                return True

            # Ищем iframe с капчей
            frames = await self.tab.select_all("iframe")
            for frame in frames:
                # Переключиться на frame через CDP? В nodriver нет прямого switch_to.
                # Альтернатива: найти элемент #js-button внутри страницы (он может быть в корне)
                try:
                    btn = await self.tab.select("#js-button", timeout=2)
                    if btn:
                        await self.human.click_element(btn)
                        self._log("Клик по confirm выполнен через элемент #js-button")
                        return True
                except Exception:
                    pass
        except Exception:
            pass
        return False