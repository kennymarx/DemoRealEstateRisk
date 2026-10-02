# -*- coding: utf-8 -*-
"""财务报表 OCR"""
import logging
from typing import List

from cache_manager import CacheManager
from llm_client import LLMClient, extract_json
from scanner import list_images

logger = logging.getLogger(__name__)


OCR_PROMPT_TEMPLATE = """你是一名专业的财务报表识别引擎。请仔细识别以下 {n} 张图片中的财务报表内容。
图片已按顺序编号为 1 ~ {n}。

识别要求：
1. 判断每张图片所属报表类型：资产负债表 / 利润表 / 现金流量表 / 所有者权益变动表 / 其他。
2. 提取报表对应的公司名称、报告年份、金额单位（元 / 万元 / 千元）。图片中未出现的填 null。
3. 逐行提取【科目名称】【列名（如期末余额/期初余额/本期金额/上期金额）】【金额】。
4. 严禁编造数据，看不清的填 null。
5. 只输出 JSON，不要输出任何解释文字，不要使用 markdown 代码块。

输出 JSON 结构：
{{
  "statements": [
    {{
      "image_index": 1,
      "company": "XX房地产开发有限公司",
      "year": "2023",
      "statement_type": "资产负债表",
      "unit": "元",
      "rows": [
        {{"item": "货币资金", "column": "期末余额", "value": 123456.78}},
        {{"item": "货币资金", "column": "期初余额", "value": 100000.00}}
      ]
    }}
  ]
}}
"""


class OcrProcessor:
    def __init__(self, llm: LLMClient, cache: CacheManager, cfg):
        self.llm = llm
        self.cache = cache
        self.cfg = cfg

    def process_dir(self, fs_dir) -> List[dict]:
        images = list_images(fs_dir, self.cfg.image_exts)
        if not images:
            logger.warning("目录 [%s] 下未找到图片", fs_dir)
            return []

        bs = self.cfg.batch_size
        batches = [images[i:i + bs] for i in range(0, len(images), bs)]
        logger.info("目录 [%s]：共 %d 张图片，分 %d 批处理", fs_dir, len(images), len(batches))

        results = []
        for idx, batch in enumerate(batches, 1):
            key = CacheManager.make_batch_key(batch)
            cached = self.cache.get(key)
            if cached is not None:
                logger.info("  批次 %d/%d 命中缓存，跳过", idx, len(batches))
                results.append(cached)
                continue

            logger.info("  批次 %d/%d：调用大模型识别 %d 张图片…", idx, len(batches), len(batch))
            prompt = OCR_PROMPT_TEMPLATE.format(n=len(batch))
            raw = self.llm.chat_with_images([str(p) for p in batch], prompt)
            try:
                parsed = extract_json(raw)
            except Exception as e:  # noqa: BLE001
                logger.error("  批次 %d 返回内容无法解析为 JSON：%s", idx, e)
                parsed = {"statements": [], "_parse_error": str(e)}

            record = {"images": [str(p) for p in batch], "raw": raw, "parsed": parsed}
            self.cache.set(key, record)
            results.append(record)
        return results


def merge_statements(batch_results: List[dict], project_name: str) -> List[dict]:
    merged: dict = {}
    order: list = []

    for br in batch_results:
        parsed = (br or {}).get("parsed") or {}
        for st in parsed.get("statements") or []:
            key = (
                (st.get("company") or "").strip(),
                str(st.get("year") or "").strip(),
                (st.get("statement_type") or "").strip(),
            )
            if key not in merged:
                merged[key] = {
                    "project": project_name,
                    "company": st.get("company"),
                    "year": st.get("year"),
                    "statement_type": st.get("statement_type"),
                    "unit": st.get("unit"),
                    "rows": [],
                    "_seen": set(),
                }
                order.append(key)

            m = merged[key]
            if not m.get("unit") and st.get("unit"):
                m["unit"] = st["unit"]
            for row in st.get("rows") or []:
                sig = (str(row.get("item") or "").strip(), str(row.get("column") or "").strip())
                if sig in m["_seen"]:
                    continue
                m["_seen"].add(sig)
                m["rows"].append(row)

    out = []
    for k in order:
        m = merged[k]
        m.pop("_seen", None)
        out.append(m)
    return out