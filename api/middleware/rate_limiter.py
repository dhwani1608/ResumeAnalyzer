from __future__ import annotations

import os

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError


class RateLimiter:
    def __init__(self):
        self.redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
        self.window_seconds = 60
        self.default_limit = int(os.getenv("RATE_LIMIT_PER_MIN", "100"))

    async def enforce(self, key_hash: str, limit: int | None = None) -> None:
        effective_limit = limit or self.default_limit
        bucket = f"rl:{key_hash}"
        try:
            current = await self.redis.incr(bucket)
            if current == 1:
                await self.redis.expire(bucket, self.window_seconds)
            if current > effective_limit:
                raise HTTPException(status_code=429, detail={"error": "rate_limited", "detail": "Rate limit exceeded", "field": "X-API-Key"})
        except RedisError:
            # Fail open when Redis is unavailable so local/dev usage still works.
            return


rate_limiter = RateLimiter()
