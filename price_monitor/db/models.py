"""
SQLAlchemy ORM 模型 — Antigravity 线上价格监测
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Index, Integer, BigInteger,
    Numeric, String, Text, JSON, ForeignKey, UniqueConstraint,
    create_engine, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class OfferSnapshot(Base):
    """报价快照 — 核心表, 每次采集的原始数据"""
    __tablename__ = "offer_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    offer_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="幂等key")
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    keyword: Mapped[Optional[str]] = mapped_column(String(100), index=True, comment="搜索关键词")
    canonical_url: Mapped[Optional[str]] = mapped_column(String(500))
    product_name: Mapped[Optional[str]] = mapped_column(String(300))
    product_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    shop_name: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    shop_url: Mapped[Optional[str]] = mapped_column(String(500))
    ship_from_city: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    raw_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    final_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    original_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    coupon_info: Mapped[Optional[dict]] = mapped_column(JSON, comment="优惠券明细")
    confidence: Mapped[str] = mapped_column(String(10), default="MED")
    sales_volume: Mapped[Optional[str]] = mapped_column(String(50))
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500))
    screenshot_hash: Mapped[Optional[str]] = mapped_column(String(64))
    parse_status: Mapped[str] = mapped_column(String(10), default="OK")
    fail_reason: Mapped[Optional[str]] = mapped_column(String(300))
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关联
    violations: Mapped[list["Violation"]] = relationship(back_populates="offer", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_platform_time", "platform", "captured_at"),
        Index("idx_final_price", "final_price"),
    )


class Violation(Base):
    """违规记录"""
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    offer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("offer_snapshots.id"), nullable=False)
    product_name: Mapped[Optional[str]] = mapped_column(String(300))
    platform: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    baseline_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    final_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gap_value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    gap_percent: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    severity: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    is_whitelisted: Mapped[bool] = mapped_column(Boolean, default=False)
    shop_name: Mapped[Optional[str]] = mapped_column(String(100))
    ship_from_city: Mapped[Optional[str]] = mapped_column(String(50))
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500))
    canonical_url: Mapped[Optional[str]] = mapped_column(String(500))
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关联
    offer: Mapped["OfferSnapshot"] = relationship(back_populates="violations")

    __table_args__ = (
        Index("idx_severity_time", "severity", "created_at"),
    )


class BaselinePrice(Base):
    """基准价 (控价基准)"""
    __tablename__ = "baseline_prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_pattern: Mapped[str] = mapped_column(String(200), nullable=False, comment="商品名匹配模式")
    sku_name: Mapped[Optional[str]] = mapped_column(String(200), comment="SKU 显示名称")
    baseline_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(300))
    updated_by: Mapped[Optional[str]] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SearchKeyword(Base):
    """搜索关键词"""
    __tablename__ = "search_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, comment="0=普通, 1=重点")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WhitelistRule(Base):
    """白名单规则"""
    __tablename__ = "whitelist_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_type: Mapped[str] = mapped_column(String(20), nullable=False, comment="SHOP/SKU/URL/PROJECT")
    match_pattern: Mapped[str] = mapped_column(String(300), nullable=False)
    platform: Mapped[Optional[str]] = mapped_column(String(20))
    reason: Mapped[Optional[str]] = mapped_column(String(300))
    approved_by: Mapped[Optional[str]] = mapped_column(String(50))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CookieAccount(Base):
    """Cookie 账号管理"""
    __tablename__ = "cookie_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    account_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cookies: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("platform", "account_id", name="uk_platform_account"),
    )


class ScrapeJob(Base):
    """采集任务跟踪"""
    __tablename__ = "scrape_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="FULL_SCAN | PLATFORM_SCAN | SINGLE_URL"
    )
    platform: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    keyword: Mapped[Optional[str]] = mapped_column(String(100))
    target_url: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING", index=True,
        comment="PENDING | RUNNING | SUCCESS | FAILED | CANCELLED",
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="0-100")
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    success_items: Mapped[int] = mapped_column(Integer, default=0)
    fail_items: Mapped[int] = mapped_column(Integer, default=0)
    violations_found: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(
        String(20), default="manual", comment="scheduler | manual | api"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_job_status_time", "status", "created_at"),
    )
