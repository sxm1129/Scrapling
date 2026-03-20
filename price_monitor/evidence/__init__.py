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

def pack_evidence(
    offer_id: int,
    screenshot_path: Optional[str],
    page_text: Optional[str] = None,
    canonical_url: str = "",
    platform: str = "",
) -> dict:
    """
    打包三合一证据包:
      1. 截图 SHA256 哈希
      2. 页面文本摘要 (innerText 前 300 字符)
      3. UTC 时间戳

    返回可序列化为 JSON 并嵌入到 OfferSnapshot.screenshot_hash 的证据包字典。
    """
    import json
    import hmac as hmac_mod

    # 1. 截图哈希
    screenshot_hash = ""
    if screenshot_path and Path(screenshot_path).exists():
        screenshot_hash = compute_hash(screenshot_path)

    # 2. 时间戳
    timestamp_utc = datetime.utcnow().isoformat() + "Z"

    # 3. 页面文本摘要
    text_preview = (page_text or "")[:300].strip().replace("\n", " ")

    # 4. 构建证据包
    evidence = {
        "offer_id": offer_id,
        "platform": platform,
        "canonical_url": canonical_url,
        "screenshot_path": screenshot_path,
        "screenshot_hash": screenshot_hash,
        "page_text_preview": text_preview,
        "captured_at_utc": timestamp_utc,
        "version": "1.0",
    }

    # 5. 内容哈希签名（防篡改）
    canonical = json.dumps(evidence, sort_keys=True, ensure_ascii=False)
    content_sig = hashlib.sha256(canonical.encode()).hexdigest()
    evidence["content_signature"] = f"sha256:{content_sig}"

    log.info(
        f"[evidence] Packed offer #{offer_id}: "
        f"screenshot={screenshot_hash[:16]}..., sig={content_sig[:16]}..."
    )
    return evidence


def verify_evidence(evidence: dict) -> bool:
    """
    校验证据包完整性。
    返回 True = 未被篡改。
    """
    import json
    import hmac as hmac_mod
    stored_sig = evidence.get("content_signature", "")
    if not stored_sig.startswith("sha256:"):
        return False
    stored_hash = stored_sig[7:]
    check = {k: v for k, v in evidence.items() if k != "content_signature"}
    canonical = json.dumps(check, sort_keys=True, ensure_ascii=False)
    expected = hashlib.sha256(canonical.encode()).hexdigest()
    return hmac_mod.compare_digest(expected, stored_hash)
