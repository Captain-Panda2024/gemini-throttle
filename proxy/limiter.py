import asyncio
import time

class TokenBucket:
    def __init__(self, rate_per_min):
        self.capacity = rate_per_min
        self.tokens = rate_per_min
        self.last_refill = time.monotonic()
        self.rate = rate_per_min / 60.0
        self.lock = asyncio.Lock()

    async def consume(self):
        async with self.lock:
            while True:
                now = time.monotonic()
                refill = (now - self.last_refill) * self.rate
                self.tokens = min(self.capacity, self.tokens + refill)
                self.last_refill = now
                
                if self.tokens >= 1:
                    self.tokens -= 1
                    return True
                
                # 待機計算: 1トークン分回復するまでの時間
                sleep_time = (1 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)
