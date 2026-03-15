"""
认证依赖 — 统一鉴权函数
"""
import os
from fastapi import HTTPException, Request


def require_auth(request: Request):
    """密码认证 — 写入操作强制校验"""
    password = os.getenv("ADMIN_PASSWORD", "kashi2026")
    auth = request.headers.get("Authorization", "")
    token = request.query_params.get("token", "")
    if auth == f"Bearer {password}" or token == password:
        return True
    raise HTTPException(401, "Authentication required")
