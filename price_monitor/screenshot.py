"""
截图引擎 — 对价格区域截图并添加时间戳水印
利用 Scrapling 的 StealthyFetcher/DynamicFetcher 内置的 Playwright 能力
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("price_monitor.screenshot")


class PriceScreenshot:
    """价格区域截图，带时间戳水印"""

    def __init__(self, output_dir: str = "./screenshots", quality: int = 85):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.quality = quality

    async def capture_element(
        self,
        page,
        selector: str,
        filename: Optional[str] = None,
        padding: int = 10,
        context_str: str = "",
    ) -> Optional[str]:
        """截取页面中指定元素区域的截图

        :param page: Playwright Page 对象 (通过 page_action 传入)
        :param selector: 要截取的 CSS 选择器
        :param filename: 输出文件名, 默认自动生成
        :param padding: 截取区域的边距 (px)
        :param context_str: 附加到水印中的上下文信息 (如 平台/URL)
        :return: 截图文件路径, 如果失败返回 None
        """
        try:
            element = page.locator(selector).first
            if not await element.is_visible():
                log.warning(f"Element not visible: {selector}")
                return None

            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"price_{timestamp}.png"

            filepath = self.output_dir / filename

            # 注入水印
            await self.add_timestamp_watermark(page, context_str=context_str)

            # 截取元素区域
            await element.screenshot(path=str(filepath))

            log.info(f"Screenshot saved: {filepath}")
            return str(filepath)

        except Exception as e:
            log.error(f"Screenshot failed for selector '{selector}': {e}")
            return None

    async def capture_full_page(
        self,
        page,
        filename: Optional[str] = None,
        context_str: str = "",
    ) -> Optional[str]:
        """截取完整页面截图

        :param page: Playwright Page 对象
        :param filename: 输出文件名
        :param context_str: 附加到水印中的上下文信息 (如 平台/URL)
        :return: 截图文件路径
        """
        try:
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"page_{timestamp}.png"

            filepath = self.output_dir / filename

            # 注入水印
            await self.add_timestamp_watermark(page, context_str=context_str)

            await page.screenshot(path=str(filepath), full_page=True)
            log.info(f"Full page screenshot saved: {filepath}")
            return str(filepath)

        except Exception as e:
            log.error(f"Full page screenshot failed: {e}")
            return None

    async def add_timestamp_watermark(
        self,
        page,
        position: str = "bottom-right",
        context_str: str = "",
    ) -> None:
        """通过 JS 注入在页面上添加时间戳水印 (在截图前调用)

        :param page: Playwright Page 对象
        :param position: 水印位置
        :param context_str: 附加上下文 (平台/短链接)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        positions = {
            "bottom-right": "bottom: 10px; right: 10px;",
            "bottom-left": "bottom: 10px; left: 10px;",
            "top-right": "top: 10px; right: 10px;",
            "top-left": "top: 10px; left: 10px;",
        }
        pos_style = positions.get(position, positions["bottom-right"])
        
        watermark_text = f"采集时间: {timestamp}"
        if context_str:
            watermark_text += f" | {context_str}"

        js_code = f"""
        (() => {{
            const watermark = document.createElement('div');
            watermark.id = 'pm-watermark';
            watermark.style.cssText = `
                position: fixed;
                {pos_style}
                background: rgba(0, 0, 0, 0.7);
                color: #fff;
                padding: 4px 10px;
                font-size: 12px;
                font-family: monospace;
                border-radius: 3px;
                z-index: 99999;
                pointer-events: none;
                white-space: pre-wrap;
            `;
            watermark.textContent = '{watermark_text}';
            document.body.appendChild(watermark);
        }})();
        """
        try:
            await page.evaluate(js_code)
        except Exception as e:
            log.warning(f"Failed to inject watermark: {e}")
