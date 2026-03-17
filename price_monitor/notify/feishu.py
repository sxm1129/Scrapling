"""
飞书 (Feishu) Webhook 通知服务
- 工单创建卡片
- SLA 超时升级告警
- 周报摘要推送
"""
import logging
import os
import httpx
from datetime import datetime, timezone

log = logging.getLogger("price_monitor.notify.feishu")

SEVERITY_EMOJI = {"P0": "🔴", "P1": "🟠", "P2": "🟡"}
STATUS_LABEL = {
    "OPEN": "待处理",
    "IN_PROGRESS": "处理中",
    "WAITING_INFO": "等待信息",
    "RESOLVED": "已解决",
    "REJECTED": "已拒绝",
}


def _default_webhook() -> str:
    return os.getenv("FEISHU_WEBHOOK_URL", "")


def _post(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        log.warning("Feishu webhook URL not configured, skipping notification")
        return False
    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0:
            log.error(f"Feishu API error: {data}")
            return False
        return True
    except Exception as e:
        log.error(f"Failed to send Feishu notification: {e}")
        return False


def send_workorder_created(
    wo: dict,
    violation: dict,
    webhook_url: str = "",
) -> bool:
    """发送新工单创建的飞书卡片消息"""
    url = webhook_url or _default_webhook()
    severity = wo.get("severity", "P1")
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    owner = wo.get("owner_name") or "待认领"
    sla_due = wo.get("sla_due_at", "")
    if hasattr(sla_due, "isoformat"):
        sla_due = sla_due.strftime("%m-%d %H:%M")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{emoji} [{severity}] 新低价违规工单 #{wo.get('id')}",
                },
                "template": "red" if severity == "P0" else "orange",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**平台**\n{wo.get('platform', '')}"}} ,
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**责任人**\n{owner}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**违规价**\n¥{wo.get('violation_price', '?')}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**基准价**\n¥{wo.get('baseline_price', '?')}"}},
                        {"is_short": False, "text": {"tag": "lark_md", "content": f"**商品**\n{wo.get('product_name', '')[:60]}"}},
                        {"is_short": False, "text": {"tag": "lark_md", "content": f"**SLA 截止**\n{sla_due}"}},
                    ],
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看工单"},
                            "type": "primary",
                            "url": f"{os.getenv('WEB_URL', 'http://localhost:3000')}/workorders/{wo.get('id')}",
                        }
                    ],
                },
            ],
        },
    }
    return _post(url, payload)


def send_sla_escalation(wo: dict, webhook_url: str = "") -> bool:
    """发送 SLA 升级告警卡片"""
    url = webhook_url or _default_webhook()
    severity = wo.get("severity", "P1")
    emoji = SEVERITY_EMOJI.get(severity, "⚪")
    level = wo.get("escalation_level", 1)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🚨 工单 #{wo.get('id')} SLA 超时升级（Level {level}）",
                },
                "template": "red",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**等级**\n{emoji} {severity}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**责任人**\n{wo.get('owner_name', '待认领')}"}},
                        {"is_short": False, "text": {"tag": "lark_md", "content": f"**商品**\n{wo.get('product_name', '')[:60]}"}},
                    ],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "立即处理"},
                            "type": "danger",
                            "url": f"{os.getenv('WEB_URL', 'http://localhost:3000')}/workorders/{wo.get('id')}",
                        }
                    ],
                },
            ],
        },
    }
    return _post(url, payload)


def send_report_ready(
    report: dict,
    kpis: dict,
    webhook_url: str = "",
) -> bool:
    """发送周报/月报摘要飞书卡片"""
    url = webhook_url or _default_webhook()
    start = report.get("start_date", "")
    end = report.get("end_date", "")
    if hasattr(start, "strftime"):
        start = start.strftime("%Y-%m-%d")
    if hasattr(end, "strftime"):
        end = end.strftime("%Y-%m-%d")

    violations_total = kpis.get("violations_total", 0)
    workorder_close_rate = kpis.get("workorder_close_rate", 0)
    sla_achievement = kpis.get("sla_achievement_rate", 0)
    top_platform = kpis.get("top_platform", "N/A")

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 Antigravity 控价周报 ({start} ~ {end})"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**低价违规总数**\n{violations_total} 条"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**工单闭环率**\n{workorder_close_rate:.1%}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**SLA 达成率**\n{sla_achievement:.1%}"}},
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**违规最多平台**\n{top_platform}"}},
                    ],
                },
                {"tag": "hr"},
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看完整报告"},
                            "type": "primary",
                            "url": f"{os.getenv('WEB_URL', 'http://localhost:3000')}/reports/{report.get('id', '')}",
                        }
                    ],
                },
            ],
        },
    }
    return _post(url, payload)
