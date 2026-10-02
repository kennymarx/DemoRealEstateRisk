# -*- coding: utf-8 -*-
"""令牌桶限流器（线程安全）"""
import threading
import time


class RateLimiter:
    def __init__(self, rate: float = 6.0, capacity: float = None):
        if rate <= 0:
            raise ValueError("rate 必须 > 0")
        self.rate = float(rate)
        self.capacity = float(capacity if capacity is not None else rate)
        self._tokens = self.capacity
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last = now

    def acquire(self, tokens: float = 1.0, timeout: float = None) -> bool:
        if tokens <= 0:
            return True
        if tokens > self.capacity:
            raise ValueError(f"请求令牌数 {tokens} 超过桶容量 {self.capacity}")

        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                need = tokens - self._tokens
                wait = need / self.rate
                if deadline is not None:
                    remain = deadline - time.monotonic()
                    if remain <= 0:
                        return False
                    wait = min(wait, remain)
            time.sleep(max(wait, 0.001))

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        return False