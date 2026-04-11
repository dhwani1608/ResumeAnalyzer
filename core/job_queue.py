from __future__ import annotations

import hashlib
import os
from typing import Any

from redis.asyncio import Redis


class JobQueue:
    def __init__(self):
        self.redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    async def enqueue(self, payload: dict[str, Any]) -> str:
        job_id = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()[:24]
        await self.redis.hset(f"job:{job_id}", mapping={"status": "queued", "payload": str(payload)})
        await self.redis.rpush("jobs:queue", job_id)
        return job_id

    async def set_status(self, job_id: str, status: str, result: str = "") -> None:
        await self.redis.hset(f"job:{job_id}", mapping={"status": status, "result": result})

    async def get_status(self, job_id: str) -> dict[str, str]:
        data = await self.redis.hgetall(f"job:{job_id}")
        return data or {"status": "not_found"}
