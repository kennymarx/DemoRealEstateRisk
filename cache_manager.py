# -*- coding: utf-8 -*-
"""OCR 缓存"""
import hashlib
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _legacy_path(self, key: str) -> Path:
        h = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.dir / f"{h}.json"

    def _path(self, key: str, label=None) -> Path:
        legacy_path = self._legacy_path(key)
        if not label:
            return legacy_path
        readable = re.sub(r'[\\/:*?"<>|]+', "_", str(label)).strip(" ._")
        readable = re.sub(r"\s+", "_", readable)[:100] or "cache"
        return self.dir / f"{readable}_{legacy_path.stem[:12]}.json"

    def get(self, key: str, label=None):
        p = self._path(key, label)
        if not p.exists() and label:
            legacy_path = self._legacy_path(key)
            if legacy_path.exists():
                try:
                    legacy_path.replace(p)
                    logger.info("旧缓存已迁移为可读文件名：%s", p.name)
                except OSError:
                    p = legacy_path
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8")).get("value")
        except Exception as e:  # noqa: BLE001
            logger.warning("缓存读取失败 %s：%s", p, e)
            return None

    def set(self, key: str, value, label=None) -> None:
        p = self._path(key, label)
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