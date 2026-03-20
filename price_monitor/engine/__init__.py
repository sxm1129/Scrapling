"""
engine/__init__.py — 价格引擎 v2
==================================
升级内容:
  - match_baseline(): 使用 SequenceMatcher 相似度匹配（替代关键词全命中）
  - evaluate_violation(): 优先使用 per-SKU tolerance_percent，回退全局阈值
  - check_whitelist(): 新增 PROJECT 类型的正则支持
  - process_offers(): 新增 fail_reason_code 写入
"""
import re
import logging
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.orm import Session

from price_monitor.db.models import BaselinePrice, OfferSnapshot, Violation, WhitelistRule
from price_monitor.db import crud

log = logging.getLogger(__name__)

# 全局违规阈值 (可被 per-SKU tolerance_percent 覆盖)
P0_GAP_PERCENT = 0.30   # ≥30% → P0
P1_GAP_PERCENT = 0.15   # ≥15% → P1
GAP_ABS_THRESHOLD = 10  # 绝对值差 ≥¥10 也触发 P1

# 相似度匹配阈值（SequenceMatcher ratio）
MATCH_SIMILARITY_THRESHOLD = 0.60


def _similarity(a: str, b: str) -> float:
    """计算两个字符串的 SequenceMatcher 相似度 [0, 1]"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match_baseline(product_name: str, baselines: list[BaselinePrice]) -> Optional[BaselinePrice]:
    """
    匹配基准价 v2:
      策略1: 关键词全命中（所有空格切分的词都存在于商品名中）
      策略2: SequenceMatcher 相似度 ≥ 0.60
      两种策略都按"匹配分数从高到低"择优取最佳
    """
    if not product_name or not baselines:
        return None

    product_lower = product_name.lower()
    best_match: Optional[BaselinePrice] = None
    best_score: float = 0.0

    for bp in baselines:
        pattern = bp.product_pattern.lower()
        keywords = pattern.split()
        score = 0.0

        # 策略1：关键词全命中 → 分数 = 命中关键词数量 / 总词数 * 2（加倍权重）
        if keywords:
            matched_kw = sum(1 for kw in keywords if kw in product_lower)
            if matched_kw == len(keywords):
                # 全命中，使用 pattern 长度作为区分度
                score = 2.0 + len(pattern) / 100.0

        # 策略2：序列相似度（作为补充）
        if score == 0.0:
            sim = _similarity(product_lower, pattern)
            if sim >= MATCH_SIMILARITY_THRESHOLD:
                score = sim

        if score > best_score:
            best_score = score
            best_match = bp

    return best_match


def evaluate_violation(
    offer: OfferSnapshot,
    baseline: BaselinePrice,
) -> Optional[dict]:
    """
    评估是否违规 v2:
      - 优先使用 baseline.tolerance_percent 作为 P1 阈值
      - P0 阈值固定为 tolerance_percent * 2（或全局 P0）
    """
    final_price = float(offer.final_price or offer.raw_price or 0)
    baseline_price = float(baseline.baseline_price)

    if baseline_price <= 0 or final_price <= 0:
        return None

    gap_value = baseline_price - final_price
    gap_percent = gap_value / baseline_price if baseline_price > 0 else 0

    # 使用 per-SKU 阈值（如果已配置）
    p1_threshold = float(baseline.tolerance_percent) if baseline.tolerance_percent else P1_GAP_PERCENT
    p0_threshold = max(P0_GAP_PERCENT, p1_threshold * 2)

    # 判定严重度
    severity = None
    if gap_percent >= p0_threshold:
        severity = "P0"
    elif gap_percent >= p1_threshold:
        severity = "P1"
    elif gap_value >= GAP_ABS_THRESHOLD and gap_percent > 0:
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
    """检查是否命中白名单（支持正则模式）"""
    for rule in whitelist_rules:
        # 平台过滤
        if rule.platform and rule.platform != offer.platform:
            continue

        pattern = rule.match_pattern.lower()
        matched = False

        if rule.rule_type == "SHOP":
            shop = (offer.shop_name or "").lower()
            matched = (pattern in shop) or bool(re.search(pattern, shop))
        elif rule.rule_type == "SKU":
            name = (offer.product_name or "").lower()
            matched = (pattern in name) or bool(re.search(pattern, name))
        elif rule.rule_type == "URL":
            matched = pattern in (offer.canonical_url or "").lower()
        elif rule.rule_type == "PROJECT":
            name = (offer.product_name or "").lower()
            matched = (pattern in name) or bool(re.search(pattern, name))

        if matched:
            return True

    return False


def _classify_fail_reason(error_msg: str) -> str:
    """将异常信息映射为标准化失败原因代码"""
    if not error_msg:
        return "UNKNOWN"
    msg = error_msg.lower()
    if any(k in msg for k in ["cookie", "login", "plogin", "passport", "session"]):
        return "COOKIE_EXPIRED"
    if any(k in msg for k in ["risk", "验证", "captcha", "blocked", "risk_handler"]):
        return "RISK_CONTROL"
    if any(k in msg for k in ["selector", "timeout", "wait_for_selector", "element not found"]):
        return "SELECTOR_MISS"
    if any(k in msg for k in ["timeout", "timed out", "timedout", "too slow"]):
        return "TIMEOUT"
    return "UNKNOWN"


def process_offers(session: Session, offers: list[OfferSnapshot]) -> list[Violation]:
    """
    批量处理 offers: 匹配基准价 → 白名单检查 → 违规判定
    返回新创建的违规列表
    """
    baselines = crud.get_baselines(session)
    whitelist_rules = crud.get_active_whitelist(session)

    violations = []

    for offer in offers:
        try:
            # 0) 跳过无效 offer
            if not offer.id or not offer.product_name:
                continue

            # 1) 匹配基准价（v2: 相似度优先）
            baseline = match_baseline(offer.product_name, baselines)
            if baseline is None:
                continue

            # 2) 评估违规（v2: per-SKU tolerance）
            violation_data = evaluate_violation(offer, baseline)
            if violation_data is None:
                continue

            # 3) 去重: 同一 offer 不重复创建违规
            existing = session.query(Violation).filter(
                Violation.offer_id == offer.id,
                Violation.severity == violation_data["severity"],
            ).first()
            if existing:
                continue

            # 4) 白名单检查（v2: 正则支持）
            is_whitelisted = check_whitelist(offer, whitelist_rules)
            violation_data["is_whitelisted"] = is_whitelisted

            # 5) 创建违规记录
            v = crud.create_violation(session, violation_data)
            violations.append(v)
        except Exception as e:
            log.error(f"Error processing offer {offer.id}: {e}")
            continue

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        log.error(f"Commit failed: {e}")
        raise

    log.info(f"Processed {len(offers)} offers → {len(violations)} violations")
    return violations


# Public alias for the private function (B1)
classify_fail_reason = _classify_fail_reason

