"""
数据 Pipeline — 统一的数据清洗、校验和存储接口
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import orjson

from price_monitor.models import ProductPrice

log = logging.getLogger("price_monitor.pipeline")


class DataPipeline:
    """数据处理管道 — 负责清洗、校验和持久化"""

    def __init__(self, output_dir: str = "./output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._items: list[dict] = []

    def process(self, item: ProductPrice) -> Optional[ProductPrice]:
        """清洗和校验单条数据"""
        # 1. 计算最终折后价
        if item.coupons and item.final_price == 0.0:
            item.calculate_final_price()

        # 2. 如果没有通过优惠券计算, 则 final_price = current_price
        if item.final_price == 0.0:
            item.final_price = item.current_price

        # 3. 基本校验
        if not item.product_id:
            log.warning(f"Dropping item: missing product_id — {item.product_name}")
            return None

        if item.current_price <= 0 and item.final_price <= 0:
            log.warning(f"Dropping item: invalid price — {item.product_id}")
            return None

        # 4. 清洗文本
        item.product_name = item.product_name.strip()
        item.shop_name = item.shop_name.strip()
        item.ship_from_city = item.ship_from_city.strip()

        # 5. 确保时间戳
        if not item.scraped_at:
            item.scraped_at = datetime.now().isoformat()

        return item

    def save_item(self, item: ProductPrice) -> bool:
        """处理并保存单条数据"""
        processed = self.process(item)
        if processed is None:
            return False

        item_dict = processed.to_dict()
        self._items.append(item_dict)
        log.info(
            f"[{processed.platform.value}] {processed.product_name} | "
            f"¥{processed.final_price:.2f} | {processed.shop_name} | {processed.ship_from_city}"
        )
        return True

    def flush_to_jsonl(self, filename: Optional[str] = None) -> str:
        """将所有缓存数据写入 JSONL 文件"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prices_{timestamp}.jsonl"

        filepath = self.output_dir / filename
        with open(filepath, "ab") as f:
            for item in self._items:
                f.write(orjson.dumps(item))
                f.write(b"\n")

        count = len(self._items)
        self._items.clear()
        log.info(f"Flushed {count} items to {filepath}")
        return str(filepath)

    def flush_to_json(self, filename: Optional[str] = None) -> str:
        """将所有缓存数据写入 JSON 文件"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"prices_{timestamp}.json"

        filepath = self.output_dir / filename
        with open(filepath, "wb") as f:
            f.write(orjson.dumps(self._items, option=orjson.OPT_INDENT_2))

        count = len(self._items)
        self._items.clear()
        log.info(f"Flushed {count} items to {filepath}")
        return str(filepath)

    @property
    def pending_count(self) -> int:
        return len(self._items)
