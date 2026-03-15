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
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return True
        log.error(f"Feishu send failed: {data}")
        return False
    except Exception as e:
        log.error(f"Feishu request failed: {e}")
        return False


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
    try:
        resp = requests.post(webhook, json=card, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            return True
        log.error(f"Feishu card failed: {data}")
        return False
    except Exception as e:
        log.error(f"Feishu card request failed: {e}")
        return False


def notify_violation(violation) -> bool:
    """推送违规告警到飞书"""
    severity = violation.severity
    icon = "🚨" if severity == "P0" else "⚠️"
    gap_pct = float(violation.gap_percent) * 100

    title = f"{icon} 低价预警 [{severity}]"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": (
                    f"**平台**: {violation.platform}  |  **店铺**: {violation.shop_name or '未知'}\n"
                    f"**商品**: {(violation.product_name or '')[:60]}\n"
                    f"**基准价**: ¥{violation.baseline_price}  →  **到手价**: ¥{violation.final_price}\n"
                    f"**差额**: -{gap_pct:.1f}% (¥{violation.gap_value})\n"
                    f"**发货城市**: {violation.ship_from_city or '未知'}"
                ),
            },
        },
    ]

    if violation.canonical_url:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看商品链接"},
                    "url": violation.canonical_url,
                    "type": "primary",
                },
            ],
        })

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
