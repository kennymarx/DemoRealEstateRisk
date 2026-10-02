# -*- coding: utf-8 -*-
"""大模型客户端：多图输入 + 重试 + JSON 解析 + 限流"""
import base64
import json
import logging
import mimetypes
import re
import time
from pathlib import Path
from typing import Any, List

import requests

from rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, cfg):
        self.cfg = cfg
        if not cfg.api_key:
            raise ValueError("未配置 api_key（可通过环境变量 LLM_API_KEY 设置）")
        url = cfg.base_url.rstrip("/")
        self.url = url if url.endswith("/chat/completions") else url + "/chat/completions"

        rate = getattr(cfg, "rate_limit_qps", 6.0) or 6.0
        burst = getattr(cfg, "rate_limit_burst", None)
        self.limiter = RateLimiter(rate=rate, capacity=burst)
        self._rate_timeout = getattr(cfg, "rate_limit_timeout", None)
        logger.info("LLM 限流已启用：rate=%.2f QPS, burst=%s", rate, burst or rate)

    def chat(self, messages: List[dict], temperature=None, max_tokens=None, retries=None) -> str:
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        retries = self.cfg.max_retries if retries is None else retries
        last_err = None
        for attempt in range(retries):
            if not self.limiter.acquire(timeout=self._rate_timeout):
                raise TimeoutError("限流等待超时，未能获取调用令牌")
            try:
                resp = requests.post(self.url, headers=headers, json=payload, timeout=self.cfg.timeout)
                if resp.status_code == 429:
                    wait = min(2 ** attempt * 2, 60)
                    logger.warning("服务端返回 429，%ds 后重试", wait)
                    time.sleep(wait)
                    raise RuntimeError("HTTP 429 Too Many Requests")
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:  # noqa: BLE001
                last_err = e
                wait = min(2 ** attempt * 2, 30)
                logger.warning("大模型调用失败（第 %d/%d 次）：%s，%ds 后重试",
                               attempt + 1, retries, e, wait)
                time.sleep(wait)
        raise RuntimeError(f"大模型调用最终失败：{last_err}")

    @staticmethod
    def encode_image(path) -> str:
        p = Path(path)
        mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
        b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    def chat_with_images(self, image_paths, prompt: str, **kwargs) -> str:
        content = [{"type": "text", "text": prompt}]
        for p in image_paths:
            content.append({"type": "image_url", "image_url": {"url": self.encode_image(p)}})
        return self.chat([{"role": "user", "content": content}], **kwargs)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Any:
    if not text or not text.strip():
        raise ValueError("大模型返回内容为空")
    t = text.strip()
    m = _FENCE_RE.search(t)
    if m:
        t = m.group(1).strip()
    else:
        starts = [i for i in (t.find("{"), t.find("[")) if i != -1]
        if starts and min(starts) > 0:
            t = t[min(starts):]
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        end = max(t.rfind("}"), t.rfind("]"))
        if end != -1:
            return json.loads(t[: end + 1])
        raise