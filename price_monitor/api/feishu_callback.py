"""
feishu_callback.py — 飞书 Bot 双向回调处理
==============================================
处理飞书卡片 action 按钮点击事件，写回 WorkOrder 状态。

卡片支持三个 action:
  - resolved     → WorkOrder.status = RESOLVED
  - escalate_p0  → WorkOrder.severity = P0 + 飞书通知升级
  - whitelist    → 创建白名单规则
"""
import hashlib
import hmac
import json
import logging
import os
import time

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from price_monitor.db.session import get_session_factory
from price_monitor.db import crud

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/feishu", tags=["feishu"])

# 飞书签名校验密钥（可选，生产环境建议启用）
_FEISHU_VERIFY_TOKEN = os.getenv("FEISHU_VERIFY_TOKEN", "")


def _verify_signature(timestamp: str, sign: str, token: str) -> bool:
    """校验飞书请求签名"""
    if not token:
        return True  # 未配置 token，跳过校验
    raw = f"{timestamp}\n{token}"
    expected = hmac.new(token.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sign)


@router.post("/callback")
async def feishu_card_callback(request: Request):
    """
    处理飞书卡片交互事件。

    飞书卡片 action 格式:
      {
        "type": "block_actions",
        "action": {
          "value": {"action": "resolved", "workorder_id": 123}
        }
      }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    # 飞书 URL 验证握手（首次配置时）
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})

    # 提取 action 数据
    action_block = body.get("action", {})
    value = action_block.get("value", {})
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {}

    action_type = value.get("action", "")
    workorder_id = value.get("workorder_id")
    operator = value.get("operator", "feishu_user")

    if not workorder_id:
        log.warning("[feishu_callback] No workorder_id in action value")
        return JSONResponse({"code": 0, "msg": "no workorder_id"})

    factory = get_session_factory()
    with factory() as session:
        wo = crud.get_workorder(session, workorder_id)
        if not wo:
            log.warning(f"[feishu_callback] WorkOrder #{workorder_id} not found")
            return JSONResponse({"code": 0, "msg": "workorder not found"})

        from datetime import datetime

        if action_type == "resolved":
            wo.status = "RESOLVED"
            wo.resolved_at = datetime.utcnow()
            wo.resolution_note = value.get("note", "飞书卡片快速处理")
            wo.resolution_type = "PRICE_FIXED"
            crud.append_workorder_action(session, workorder_id, {
                "type": "RESOLVED_VIA_FEISHU",
                "operator": operator,
                "note": "通过飞书卡片标记已处理",
            })
            log.info(f"[feishu_callback] WO#{workorder_id} marked RESOLVED by {operator}")

        elif action_type == "escalate_p0":
            wo.severity = "P0"
            wo.escalation_level = (wo.escalation_level or 0) + 1
            crud.append_workorder_action(session, workorder_id, {
                "type": "ESCALATED_P0_VIA_FEISHU",
                "operator": operator,
                "note": "通过飞书卡片升级为 P0",
            })
            log.info(f"[feishu_callback] WO#{workorder_id} escalated to P0 by {operator}")

        elif action_type == "whitelist":
            shop_name = value.get("shop_name", "")
            platform = value.get("platform", wo.platform)
            if shop_name:
                crud.create_whitelist(session, {
                    "rule_type": "SHOP",
                    "match_pattern": shop_name,
                    "platform": platform,
                    "reason": f"飞书卡片快速白名单, WO#{workorder_id}",
                    "approved_by": operator,
                })
                wo.status = "RESOLVED"
                wo.resolution_type = "WHITELIST_ADDED"
                crud.append_workorder_action(session, workorder_id, {
                    "type": "WHITELIST_ADDED_VIA_FEISHU",
                    "operator": operator,
                    "note": f"加白名单: {shop_name}",
                })
                log.info(f"[feishu_callback] WO#{workorder_id} whitelist added: {shop_name}")

        elif action_type == "waiting_info":
            wo.status = "WAITING_INFO"
            crud.append_workorder_action(session, workorder_id, {
                "type": "WAITING_INFO_VIA_FEISHU",
                "operator": operator,
                "note": "飞书卡片标记等待信息",
            })

        else:
            log.warning(f"[feishu_callback] Unknown action_type: {action_type}")
            return JSONResponse({"code": 0, "msg": f"unknown action: {action_type}"})

        session.commit()

    return JSONResponse({"code": 0, "msg": "ok"})
