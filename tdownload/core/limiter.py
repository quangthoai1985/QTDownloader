"""Giới hạn tốc độ kiểu token bucket (dùng chung cho nhiều kết nối)."""

from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, rate_bps: float = 0):
        self.rate = float(rate_bps)
        self._tokens = 0.0
        self._last = time.monotonic()

    def set_rate(self, rate_bps: float) -> None:
        self.rate = float(rate_bps)
        self._tokens = 0.0
        self._last = time.monotonic()

    @property
    def enabled(self) -> bool:
        return self.rate > 0

    async def consume(self, n: int) -> None:
        rate = self.rate
        if rate <= 0:
            return
        t = time.monotonic()
        # cho phép "dồn" tối đa 0,25 giây để tốc độ mượt nhưng không vượt trần
        self._tokens = min(rate * 0.25, self._tokens + (t - self._last) * rate)
        self._last = t
        self._tokens -= n
        if self._tokens < 0:
            await asyncio.sleep(-self._tokens / rate)

    def read_size(self, default: int) -> int:
        """Đọc từng mảnh nhỏ hơn khi bị giới hạn để tránh giật cục."""
        if self.rate <= 0:
            return default
        return int(max(4096, min(default, self.rate / 8)))
