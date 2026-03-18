"""
human_actions.py — 全人类行为仿真库
=====================================
提供真实用户级别的浏览器操作模拟:
  - 贝塞尔曲线鼠标轨迹
  - 逐字打字（随机延迟）
  - 拟真滚动（渐进加速+减速）
  - 拟真阅读停顿
"""
import asyncio
import logging
import math
import random
from typing import Optional

from patchright.async_api import Page, ElementHandle

log = logging.getLogger("price_monitor.playwright_engine.human_actions")


def _bezier_point(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """标准三次贝塞尔公式"""
    return (
        (1 - t) ** 3 * p0
        + 3 * (1 - t) ** 2 * t * p1
        + 3 * (1 - t) * t ** 2 * p2
        + t ** 3 * p3
    )


def _generate_bezier_path(
    x0: float, y0: float, x1: float, y1: float, steps: int = 20
) -> list[tuple[float, float]]:
    """
    生成从 (x0,y0) 到 (x1,y1) 的贝塞尔曲线路径点。
    控制点随机偏移以模拟手抖。
    """
    # 随机控制点（在起终点之间，加入偏移噪声）
    cp1x = x0 + random.uniform(0.1, 0.4) * (x1 - x0) + random.uniform(-60, 60)
    cp1y = y0 + random.uniform(0.1, 0.4) * (y1 - y0) + random.uniform(-60, 60)
    cp2x = x0 + random.uniform(0.6, 0.9) * (x1 - x0) + random.uniform(-60, 60)
    cp2y = y0 + random.uniform(0.6, 0.9) * (y1 - y0) + random.uniform(-60, 60)

    path = []
    for i in range(steps + 1):
        t = i / steps
        x = _bezier_point(x0, cp1x, cp2x, x1, t)
        y = _bezier_point(y0, cp1y, cp2y, y1, t)
        path.append((x, y))
    return path


class HumanActions:
    """
    包装 Playwright Page，提供拟真人类操作 API。
    所有方法均为 async。
    """

    def __init__(self, page: Page):
        self.page = page

    # ── 鼠标移动 ──

    async def bezier_move(self, x: float, y: float, steps: int = 25):
        """
        通过贝塞尔曲线将鼠标从当前位置移动到 (x, y)。
        每步加入微小随机停顿（5-20ms），模拟真实手速变化。
        """
        # 获取当前鼠标位置（Playwright 没有直接 API，用 JS 获取）
        try:
            pos = await self.page.evaluate(
                "() => ({ x: window._mouseX || 0, y: window._mouseY || 0 })"
            )
            cur_x, cur_y = pos.get("x", 0), pos.get("y", 0)
        except Exception:
            cur_x, cur_y = 0, 0

        path = _generate_bezier_path(cur_x, cur_y, x, y, steps)
        for px, py in path:
            await self.page.mouse.move(px, py)
            await asyncio.sleep(random.uniform(0.005, 0.02))

        # 更新内存中的鼠标位置
        try:
            await self.page.evaluate(
                f"() => {{ window._mouseX = {x}; window._mouseY = {y}; }}"
            )
        except Exception:
            pass

    async def human_click(
        self,
        selector: str,
        move_first: bool = True,
        pre_pause_ms: int = 200,
    ):
        """
        移动到元素（贝塞尔曲线），停顿，然后点击。
        """
        elem = await self.page.wait_for_selector(selector, timeout=10_000)
        if not elem:
            raise ValueError(f"Element not found: {selector}")

        box = await elem.bounding_box()
        if not box:
            raise ValueError(f"Cannot get bounding box for: {selector}")

        # 随机点击元素内部某点（不总是正中心）
        target_x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        target_y = box["y"] + box["height"] * random.uniform(0.3, 0.7)

        if move_first:
            await self.bezier_move(target_x, target_y)

        await self.random_pause(pre_pause_ms, pre_pause_ms + 200)
        await self.page.mouse.click(target_x, target_y)
        log.debug(f"Human click: {selector} at ({target_x:.0f}, {target_y:.0f})")

    # ── 键盘输入 ──

    async def human_type(
        self,
        selector: str,
        text: str,
        clear_first: bool = True,
        char_delay_ms: tuple[int, int] = (60, 180),
    ):
        """
        逐字符打字，每个字符之间随机延迟，模拟真实打字节奏。
        中文字符会被直接 fill() 因为 type() 对 IME 处理有限。
        """
        await self.human_click(selector)

        if clear_first:
            await self.page.fill(selector, "")  # 清空现有内容
            await self.random_pause(100, 300)

        # 检测是否含有中文（中文用 fill 一次性输入更稳定）
        has_chinese = any("\u4e00" <= c <= "\u9fff" for c in text)
        if has_chinese:
            # 混合内容：分段处理
            buffer = ""
            for char in text:
                if "\u4e00" <= char <= "\u9fff":
                    if buffer:
                        await self.page.keyboard.type(buffer)
                        buffer = ""
                    await self.page.keyboard.type(char)
                else:
                    buffer += char
                    if len(buffer) > 1 and random.random() < 0.3:
                        await self.page.keyboard.type(buffer)
                        buffer = ""
                await asyncio.sleep(random.uniform(char_delay_ms[0] / 1000, char_delay_ms[1] / 1000))
            if buffer:
                await self.page.keyboard.type(buffer)
        else:
            await self.page.keyboard.type(text, delay=random.uniform(*char_delay_ms))

        log.debug(f"Human type into {selector}: '{text}'")

    # ── 滚动 ──

    async def human_scroll(
        self,
        distance_px: int = 600,
        direction: str = "down",
        steps: int = 8,
    ):
        """
        渐进式滚动，有加速和减速曲线，模拟自然手指滑动。
        """
        multiplier = 1 if direction == "down" else -1
        # 使用 ease-in-out 曲线分配每步滚动量
        total = 0
        for i in range(steps):
            t = i / (steps - 1)
            # Ease-in-out: 3t^2 - 2t^3
            ease = 3 * t ** 2 - 2 * t ** 3
            next_total = ease * distance_px
            step_delta = next_total - total
            total = next_total
            await self.page.mouse.wheel(0, step_delta * multiplier)
            await asyncio.sleep(random.uniform(0.03, 0.1))

        log.debug(f"Human scroll: {direction} {distance_px}px in {steps} steps")

    # ── 停顿 ──

    async def random_pause(self, min_ms: int = 500, max_ms: int = 1500):
        """随机停顿，模拟人工停留间隙"""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    async def simulate_reading(self, duration_s: float = 3.0):
        """
        模拟阅读页面：随机滚动 + 停顿 + 偶尔滚回。
        适用于商品详情页停留，提升账号行为得分。
        """
        log.debug(f"Simulating reading for {duration_s}s")
        elapsed = 0.0
        while elapsed < duration_s:
            action = random.choice(["scroll_down", "pause", "scroll_up", "pause", "pause"])
            if action == "scroll_down":
                dist = random.randint(100, 400)
                await self.human_scroll(dist, "down", steps=5)
                elapsed += 0.5
            elif action == "scroll_up" and elapsed > 1.0:
                dist = random.randint(50, 200)
                await self.human_scroll(dist, "up", steps=3)
                elapsed += 0.3
            else:
                pause = random.uniform(0.5, 1.5)
                await asyncio.sleep(pause)
                elapsed += pause
