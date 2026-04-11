from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

import httpx
from redis.asyncio import Redis


class WebhookRegistry:
    def __init__(self):
        self.redis = Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
        self.secret = os.getenv("WEBHOOK_SECRET", "change-me")

    async def register(self, callback_url: str) -> str:
        hook_id = hashlib.sha256(callback_url.encode("utf-8")).hexdigest()[:24]
        await self.redis.hset(f"webhook:{hook_id}", mapping={"url": callback_url})
        return hook_id

    async def list_urls(self) -> list[str]:
        keys = await self.redis.keys("webhook:*")
        urls: list[str] = []
        for key in keys:
            data = await self.redis.hgetall(key)
            if data.get("url"):
                urls.append(data["url"])
        return urls

    async def notify_all(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers = {"X-Signature": sig, "Content-Type": "application/json"}
        urls = await self.list_urls()
        async with httpx.AsyncClient(timeout=10) as client:
            for url in urls:
                try:
                    await client.post(url, content=body, headers=headers)
                except Exception:
                    continue


webhooks = WebhookRegistry()
