"""
全局配置系统
支持环境变量覆盖和 YAML 文件加载
"""

import os
from dataclasses import dataclass, field



@dataclass
class ProxyConfig:
    """代理配置"""
    provider: str = "custom"  # custom / dataimpulse / smartproxy
    api_key: str = ""
    pool_size: int = 100
    rotation_strategy: str = "round_robin"  # round_robin / random / sticky
    # 自定义代理列表文件 (每行一个 http://user:pass@host:port)
    proxy_file: str = ""


@dataclass
class StorageConfig:
    """存储配置"""
    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "price_monitor"

    # Redis (Cookie 池 + 任务队列)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # OSS (截图存储)
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key: str = ""
    oss_access_secret: str = ""


@dataclass
class CaptchaConfig:
    """验证码服务配置"""
    provider: str = "2captcha"  # 2captcha / anticaptcha / manual
    api_key: str = ""
    timeout: int = 120  # 秒


@dataclass
class ScrapingConfig:
    """采集通用配置"""
    # 全局请求间隔 (秒)
    default_delay: float = 3.0
    # 最大重试
    max_retries: int = 3
    # 浏览器超时 (毫秒)
    browser_timeout: int = 30000
    # 是否 headless
    headless: bool = True
    # 截图质量 (0-100)
    screenshot_quality: int = 85
    # User-Agent 伪装目标
    impersonate: str = "chrome"


@dataclass
class PlatformConfig:
    """单平台配置"""
    enabled: bool = True
    delay: float = 3.0  # 平台专属间隔
    max_concurrent: int = 2
    proxy_required: bool = True
    login_required: bool = False
    # 采集策略: http_api / browser / app_protocol
    strategy: str = "browser"


@dataclass
class Config:
    """主配置"""
    proxy: ProxyConfig = field(default_factory=ProxyConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)

    # 各平台配置
    platforms: dict[str, PlatformConfig] = field(default_factory=lambda: {
        "taobao": PlatformConfig(delay=5.0, login_required=True, strategy="browser"),
        "tmall": PlatformConfig(delay=5.0, login_required=True, strategy="browser"),
        "pinduoduo": PlatformConfig(delay=3.0, strategy="app_protocol"),
        "douyin": PlatformConfig(delay=4.0, strategy="browser"),
        "xiaohongshu": PlatformConfig(delay=8.0, strategy="browser"),
        "meituan_flash": PlatformConfig(delay=2.0, strategy="http_api"),
        "jd_express": PlatformConfig(delay=3.0, strategy="browser"),
        "taobao_flash": PlatformConfig(delay=5.0, login_required=True, strategy="browser"),
        "pupu": PlatformConfig(delay=3.0, strategy="app_protocol"),
        "xiaoxiang": PlatformConfig(delay=3.0, strategy="app_protocol"),
        "dingdong": PlatformConfig(delay=3.0, strategy="app_protocol"),
        "community_group": PlatformConfig(delay=5.0, strategy="app_protocol"),
    })

    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置 (优先级最高)"""
        config = cls()

        # Storage — primary env var names match .env (DB_*), PM_MYSQL_* overrides
        config.storage.mysql_host = os.getenv("PM_MYSQL_HOST", os.getenv("DB_HOST", config.storage.mysql_host))
        config.storage.mysql_port = int(os.getenv("PM_MYSQL_PORT", os.getenv("DB_PORT", str(config.storage.mysql_port))))
        config.storage.mysql_user = os.getenv("PM_MYSQL_USER", os.getenv("DB_USER", config.storage.mysql_user))
        config.storage.mysql_password = os.getenv("PM_MYSQL_PASSWORD", os.getenv("DB_PASSWORD", config.storage.mysql_password))
        config.storage.mysql_database = os.getenv("PM_MYSQL_DATABASE", os.getenv("DB_NAME", config.storage.mysql_database))

        config.storage.redis_host = os.getenv("PM_REDIS_HOST", config.storage.redis_host)
        config.storage.redis_port = int(os.getenv("PM_REDIS_PORT", str(config.storage.redis_port)))
        config.storage.redis_password = os.getenv("PM_REDIS_PASSWORD", config.storage.redis_password)

        config.storage.oss_endpoint = os.getenv("PM_OSS_ENDPOINT", config.storage.oss_endpoint)
        config.storage.oss_bucket = os.getenv("PM_OSS_BUCKET", config.storage.oss_bucket)
        config.storage.oss_access_key = os.getenv("PM_OSS_ACCESS_KEY", config.storage.oss_access_key)
        config.storage.oss_access_secret = os.getenv("PM_OSS_ACCESS_SECRET", config.storage.oss_access_secret)

        # Captcha
        config.captcha.provider = os.getenv("PM_CAPTCHA_PROVIDER", config.captcha.provider)
        config.captcha.api_key = os.getenv("PM_CAPTCHA_API_KEY", config.captcha.api_key)

        # Proxy
        config.proxy.api_key = os.getenv("PM_PROXY_API_KEY", config.proxy.api_key)
        config.proxy.proxy_file = os.getenv("PM_PROXY_FILE", config.proxy.proxy_file)

        return config
