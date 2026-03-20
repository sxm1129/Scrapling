"""
飞书 Webhook 通知服务
"""
import json
import logging
import os
from typing import Optional

import requests

log = logging.getLogger(__name__)

WEBHOOK_URL = None


def _get_webhook() -> str:
    global WEBHOOK_URL
    if WEBHOOK_URL is None:
        from dotenv import load_dotenv
        from pathlib import Path
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK", "")
    return WEBHOOK_URL


WEBHOOK_TIMEOUT = 15
WEBHOOK_MAX_RETRIES = 3


def send_text(text: str) -> bool:
    """发送纯文本消息到飞书"""
    webhook = _get_webhook()
    if not webhook:
        log.warning("FEISHU_WEBHOOK not configured, skip notification")
        return False

    payload = {
        "msg_type": "text",
        "content": {"text": text},
    }
    return _post_webhook(webhook, payload)


def send_rich_card(title: str, elements: list[dict]) -> bool:
    """发送富文本卡片消息"""
    webhook = _get_webhook()
    if not webhook:
        log.warning("FEISHU_WEBHOOK not configured")
        return False

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "red" if "P0" in title else ("orange" if "P1" in title else "blue"),
            },
            "elements": elements,
        },
    }
    return _post_webhook(webhook, card)


def _post_webhook(url: str, payload: dict) -> bool:
    """发送 Webhook 请求 (带重试)"""
    import time
    for attempt in range(WEBHOOK_MAX_RETRIES):
        try:
            resp = requests.post(url, json=payload, timeout=WEBHOOK_TIMEOUT)
            try:
                data = resp.json()
            except ValueError:
                log.error(f"Feishu response not JSON: {resp.text[:200]}")
                return False
            if data.get("code") == 0:
                return True
            log.error(f"Feishu send failed (attempt {attempt+1}): {data}")
        except requests.exceptions.Timeout:
            log.warning(f"Feishu timeout (attempt {attempt+1}/{WEBHOOK_MAX_RETRIES})")
        except requests.exceptions.ConnectionError as e:
            log.error(f"Feishu connection error (attempt {attempt+1}): {e}")
        except Exception as e:
            log.error(f"Feishu unexpected error: {e}")
            return False
        if attempt < WEBHOOK_MAX_RETRIES - 1:
            time.sleep(2 ** attempt)  # 1s, 2s backoff
    return False


def notify_violation(violation, workorder_id: int = None) -> bool:
    """推送违规告警到飞书（卡片带操作按鈕）"""
    severity = violation.severity
    icon = "🚨" if severity == "P0" else "⚠️"
    gap_pct = float(violation.gap_percent) * 100

    title = f"{icon} 低价预警 [{severity}]"

    content_md = (
        f"**平台**: {violation.platform}  |  **店铺**: {violation.shop_name or '未知'}\n"
        f"**商品**: {(violation.product_name or '')[:60]}\n"
        f"**基准价**: ¥{violation.baseline_price}  \u2192  **到手价**: ¥{violation.final_price}\n"
        f"**差额**: -{gap_pct:.1f}% (¥{violation.gap_value})\n"
        f"**发货城市**: {violation.ship_from_city or '未知'}"
    )
    if workorder_id:
        content_md += f"  |  **工单**: #{workorder_id}"

    elements = [
        {
            "tag": "div",
            "text": {"tag": "lark_md", "content": content_md},
        },
    ]

    # 商品链接按鈕
    action_buttons = []
    if violation.canonical_url:
        action_buttons.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看商品"},
            "url": violation.canonical_url,
            "type": "default",
        })

    # 工单操作按鈕（双向回调必须有 workorder_id）
    if workorder_id:
        action_buttons.extend([
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 已处理"},
                "type": "primary",
                "value": {"action": "resolved", "workorder_id": workorder_id},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⏫ 升级P0"},
                "type": "danger",
                "value": {"action": "escalate_p0", "workorder_id": workorder_id},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🟢 加白名单"},
                "type": "default",
                "value": {
                    "action": "whitelist",
                    "workorder_id": workorder_id,
                    "shop_name": violation.shop_name or "",
                    "platform": violation.platform,
                },
            },
        ])

    if action_buttons:
        elements.append({"tag": "action", "actions": action_buttons})

    return send_rich_card(title, elements)


def notify_scan_summary(
    keyword: str,
    total_offers: int,
    new_violations: int,
    p0_count: int,
    p1_count: int,
    duration_sec: float,
) -> bool:
    """推送扫描轮次汇总"""
    title = "📊 扫描轮次完成"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**关键词**: {keyword}\n"
                    f"**采集商品**: {total_offers} 条\n"
                    f"**新增违规**: {new_violations} 条 (P0: {p0_count}, P1: {p1_count})\n"
                    f"**耗时**: {duration_sec:.1f}s"
                ),
            },
        },
    ]

    return send_rich_card(title, elements)


def notify_cookie_expired(platform: str, account_id: str) -> bool:
    """Cookie 过期告警"""
    title = "⚠️ Cookie 过期提醒"
    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**平台**: {platform}\n"
                    f"**账号**: {account_id}\n"
                    f"请尽快在 Web 管理后台重新登录并更新 Cookie"
                ),
            },
        },
    ]
    return send_rich_card(title, elements)
