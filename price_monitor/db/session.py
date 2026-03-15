"""
数据库会话管理
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from price_monitor.db.models import Base

# 加载 .env
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)


def get_db_url() -> str:
    """从环境变量构建 MySQL URL"""
    from urllib.parse import quote_plus
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "3306")
    user = os.getenv("DB_USER", "root")
    password = quote_plus(os.getenv("DB_PASSWORD", ""))
    db_name = os.getenv("DB_NAME", "dolphinkashi")
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{db_name}?charset=utf8mb4"


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_db_url(),
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            echo=False,
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_db() -> Session:
    """获取数据库会话 (用于 FastAPI 依赖注入)"""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db():
    """初始化数据库 — 建表 + 插入初始数据"""
    engine = get_engine()
    Base.metadata.create_all(engine)

    # 插入初始关键词
    factory = get_session_factory()
    session = factory()
    try:
        from price_monitor.db.models import SearchKeyword
        existing = session.query(SearchKeyword).count()
        if existing == 0:
            defaults = [
                SearchKeyword(keyword="卡士酸奶", priority=1),
                SearchKeyword(keyword="卡士007", priority=1),
                SearchKeyword(keyword="卡士鲜酪乳", priority=0),
                SearchKeyword(keyword="卡士原态酪乳", priority=0),
                SearchKeyword(keyword="CLASSY KISS 酸奶", priority=0),
            ]
            session.add_all(defaults)
            session.commit()
            print(f"  Inserted {len(defaults)} default keywords")
    finally:
        session.close()
