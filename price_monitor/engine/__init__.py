"""
价格引擎 — 基准价匹配 + 违规判定
"""
import re
import logging
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from price_monitor.db.models import BaselinePrice, OfferSnapshot, Violation, WhitelistRule
from price_monitor.db import crud

log = logging.getLogger(__name__)

# 违规阈值 (可配置)
P0_GAP_PERCENT = 0.30   # ≥30% → P0
P1_GAP_PERCENT = 0.15   # ≥15% → P1
GAP_ABS_THRESHOLD = 10  # 绝对值 ≥¥10


def match_baseline(product_name: str, baselines: list[BaselinePrice]) -> Optional[BaselinePrice]:
    """匹配基准价: 用 product_pattern 做模糊匹配"""
    if not product_name or not baselines:
        return None

    product_lower = product_name.lower()
    best_match = None
    best_score = 0

    for bp in baselines:
        pattern = bp.product_pattern.lower()
        # 精确包含
        if pattern in product_lower:
            score = len(pattern)  # 越长的匹配越精确
            if score > best_score:
                best_score = score
                best_match = bp

    return best_match


def evaluate_violation(
    offer: OfferSnapshot,
    baseline: BaselinePrice,
) -> Optional[dict]:
    """
    评估是否违规
    返回 violation dict 或 None
    """
    final_price = float(offer.final_price or offer.raw_price or 0)
    baseline_price = float(baseline.baseline_price)

    if baseline_price <= 0 or final_price <= 0:
        return None

    gap_value = baseline_price - final_price
    gap_percent = gap_value / baseline_price if baseline_price > 0 else 0

    # 判定严重度
    severity = None
    if gap_percent >= P0_GAP_PERCENT:
        severity = "P0"
    elif gap_percent >= P1_GAP_PERCENT:
        severity = "P1"
    elif gap_value >= GAP_ABS_THRESHOLD:
        severity = "P1"

    if severity is None:
        return None

    return {
        "offer_id": offer.id,
        "product_name": offer.product_name,
        "platform": offer.platform,
        "baseline_price": Decimal(str(baseline_price)),
        "final_price": Decimal(str(final_price)),
        "gap_value": Decimal(str(round(gap_value, 2))),
        "gap_percent": Decimal(str(round(gap_percent, 4))),
        "severity": severity,
        "is_whitelisted": False,
        "shop_name": offer.shop_name,
        "ship_from_city": offer.ship_from_city,
        "screenshot_path": offer.screenshot_path,
        "canonical_url": offer.canonical_url,
    }


def check_whitelist(
    offer: OfferSnapshot,
    whitelist_rules: list[WhitelistRule],
) -> bool:
    """检查是否命中白名单"""
    for rule in whitelist_rules:
        # 平台过滤
        if rule.platform and rule.platform != offer.platform:
            continue

        pattern = rule.match_pattern.lower()
        matched = False

        if rule.rule_type == "SHOP":
            matched = pattern in (offer.shop_name or "").lower()
        elif rule.rule_type == "SKU":
            matched = pattern in (offer.product_name or "").lower()
        elif rule.rule_type == "URL":
            matched = pattern in (offer.canonical_url or "").lower()
        elif rule.rule_type == "PROJECT":
            # 项目白名单匹配商品名
            matched = pattern in (offer.product_name or "").lower()

        if matched:
            return True

    return False


def process_offers(session: Session, offers: list[OfferSnapshot]) -> list[Violation]:
    """
    批量处理 offers: 匹配基准价 → 白名单检查 → 违规判定
    返回新创建的违规列表
    """
    baselines = crud.get_baselines(session)
    whitelist_rules = crud.get_active_whitelist(session)

    violations = []

    for offer in offers:
        # 1) 匹配基准价
        baseline = match_baseline(offer.product_name, baselines)
        if baseline is None:
            continue

        # 2) 评估违规
        violation_data = evaluate_violation(offer, baseline)
        if violation_data is None:
            continue

        # 3) 白名单检查
        is_whitelisted = check_whitelist(offer, whitelist_rules)
        violation_data["is_whitelisted"] = is_whitelisted

        # 4) 创建违规记录
        v = crud.create_violation(session, violation_data)
        violations.append(v)

    session.commit()
    log.info(f"Processed {len(offers)} offers → {len(violations)} violations")
    return violations
