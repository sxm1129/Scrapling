"""
test_phase1.py — Phase 1 unit / smoke tests
"""
import asyncio
import sys
import os
import pytest

# ── Human Actions（无需浏览器的纯逻辑测试）──

def test_bezier_path_length():
    """贝塞尔路径生成产生正确数量的点"""
    from price_monitor.playwright_engine.human_actions import _generate_bezier_path
    path = _generate_bezier_path(0, 0, 100, 100, steps=20)
    assert len(path) == 21  # steps + 1

def test_bezier_start_end():
    """起点和终点坐标吻合（容差 5px）"""
    from price_monitor.playwright_engine.human_actions import _generate_bezier_path
    path = _generate_bezier_path(0, 0, 200, 300, steps=30)
    start_x, start_y = path[0]
    end_x, end_y = path[-1]
    assert abs(start_x - 0) < 5
    assert abs(start_y - 0) < 5
    assert abs(end_x - 200) < 5
    assert abs(end_y - 300) < 5

# ── Cookie Bridge（DB 需要可用，集成测试跳过 in CI）──

@pytest.mark.skipif("CI" in os.environ, reason="Requires DB in non-CI mode")
def test_cookie_bridge_load_no_crash():
    """CookieBridge.load_raw_cookies 不抛出异常（即使无数据）"""
    from price_monitor.playwright_engine.cookie_bridge import CookieBridge
    bridge = CookieBridge("taobao")
    # Should return None gracefully if no DB cookies
    result = bridge._load_raw_cookies()
    # result is None or (account_id, []) — no uncaught exceptions

# ── Base Scraper 数据模型 ──

def test_product_detail_to_dict():
    """ProductDetail.to_product_price_dict 返回预期键"""
    from decimal import Decimal
    from price_monitor.playwright_engine.base_scraper import ProductDetail, CouponDetail

    coupon = CouponDetail(coupon_type="CASH", threshold=Decimal("100"), discount=Decimal("10"), raw_text="满100减10")
    detail = ProductDetail(
        platform="taobao",
        keyword="酸奶",
        url="https://taobao.com/abc",
        title="卡士酸奶 1kg",
        display_price=Decimal("39.9"),
        final_price=Decimal("29.9"),
        coupons=[coupon],
        shop_name="官方旗舰店",
        ship_from_city="上海",
    )
    d = detail.to_product_price_dict()
    assert d["platform"] == "taobao"
    assert d["price"] == 29.9
    assert len(d["coupons"]) == 1
    assert d["coupons"][0]["type"] == "CASH"
    assert d["shop_name"] == "官方旗舰店"

def test_product_detail_zero_price_fallback():
    """当 final_price 为 None 时 fallback 到 display_price"""
    from decimal import Decimal
    from price_monitor.playwright_engine.base_scraper import ProductDetail

    detail = ProductDetail(
        platform="jd",
        keyword="test",
        url="https://jd.com/123",
        display_price=Decimal("59.9"),
        final_price=None,
    )
    d = detail.to_product_price_dict()
    assert d["price"] == 59.9

# ── Fallback Engine 初始化 ──

def test_engine_resume():
    """测试 pause + resume 逻辑"""
    from price_monitor.playwright_engine.fallback import PlaywrightFallbackEngine
    engine = PlaywrightFallbackEngine()
    engine._paused.add("taobao")
    assert "taobao" in engine._paused
    engine.resume("taobao")
    assert "taobao" not in engine._paused

def test_engine_auto_pause():
    """连续失败 MAX 次后平台被自动暂停"""
    from price_monitor.playwright_engine.fallback import PlaywrightFallbackEngine, MAX_CONSECUTIVE_FAILS
    engine = PlaywrightFallbackEngine()
    for _ in range(MAX_CONSECUTIVE_FAILS):
        engine._increment_fail("pdd")
    assert "pdd" in engine._paused
