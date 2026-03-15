"""
证据链 — 截图水印 + SHA256 完整性校验
"""
import hashlib
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def add_watermark(
    image_path: str,
    platform: str,
    url: str = "",
    city: str = "",
    job_id: str = "",
) -> str:
    """给截图添加水印, 返回带水印的文件路径"""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)

        # 水印文本
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        short_url = url[:60] + "..." if len(url) > 60 else url
        lines = [
            f"[{platform}] {now}",
            f"URL: {short_url}",
        ]
        if city:
            lines.append(f"City: {city}")
        if job_id:
            lines.append(f"Job: {job_id[:16]}")
        text = "\n".join(lines)

        # 字体 (尝试系统字体, fallback 到默认)
        font_size = max(14, img.width // 50)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", font_size)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", font_size)
            except (OSError, IOError):
                font = ImageFont.load_default()

        # 半透明背景
        x, y = 10, img.height - (font_size + 6) * len(lines) - 10
        for line in lines:
            bbox = draw.textbbox((x, y), line, font=font)
            draw.rectangle([bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2], fill=(0, 0, 0, 160))
            draw.text((x, y), line, fill=(255, 255, 255), font=font)
            y += font_size + 6

        # 保存
        watermarked_path = image_path.replace(".png", "_wm.png").replace(".jpg", "_wm.jpg")
        if watermarked_path == image_path:
            watermarked_path = image_path + "_wm.png"
        img.save(watermarked_path, quality=90)
        return watermarked_path

    except ImportError:
        log.warning("Pillow not installed, skipping watermark")
        return image_path
    except Exception as e:
        log.error(f"Watermark failed: {e}")
        return image_path


def compute_hash(file_path: str) -> str:
    """计算文件 SHA256 hash"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return f"sha256:{sha256.hexdigest()}"
    except (IOError, OSError) as e:
        log.error(f"Hash compute failed for {file_path}: {e}")
        return ""


def ensure_screenshot_dir(base_dir: str = None) -> Path:
    """确保截图目录存在"""
    if base_dir is None:
        base_dir = os.getenv("SCREENSHOT_DIR", "./data/screenshots")
    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    # 按日期分目录
    today = datetime.now().strftime("%Y%m%d")
    daily_dir = path / today
    daily_dir.mkdir(exist_ok=True)
    return daily_dir
