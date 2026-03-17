"""
认证依赖 — 统一鉴权函数
"""
import hmac
import logging
import os
from fastapi import HTTPException, Request

log = logging.getLogger(__name__)


def require_auth(request: Request):
    """密码认证 — 写入操作强制校验（常量时间比较，防计时攻击）"""
    password = os.getenv("ADMIN_PASSWORD", "")
    if not password:
        log.error("ADMIN_PASSWORD env var not set — all write operations are blocked!")
        raise HTTPException(503, "Service misconfigured: ADMIN_PASSWORD not set")

    auth = request.headers.get("Authorization", "")
    token = request.query_params.get("token", "")

    # Use hmac.compare_digest to prevent timing attacks
    bearer_match = hmac.compare_digest(auth, f"Bearer {password}")
    token_match = hmac.compare_digest(token, password)
    if bearer_match or token_match:
        return True
    raise HTTPException(401, "Authentication required")
