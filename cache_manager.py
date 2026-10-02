# -*- coding: utf-8 -*-
"""OCR 缓存"""
import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        h = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.dir / f"{h}.json"

    def get(self, key: str):
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8")).get("value")
        except Exception as e:  # noqa: BLE001
            logger.warning("缓存读取失败 %s：%s", p, e)
            return None

    def set(self, key: str, value) -> None:
        p = self._path(key)
        p.write_text(
            json.dumps({"key": key, "value": value}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def make_batch_key(images) -> str:
        h = hashlib.md5()
        for p in images:
            p = Path(p)
            try:
                st = p.stat()
                h.update(f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8"))
            except OSError:
                h.update(str(p).encode("utf-8"))
        return "ocr_batch::" + h.hexdigest()