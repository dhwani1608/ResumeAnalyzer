from __future__ import annotations

import asyncio
import json

from core.job_queue import JobQueue
from api.middleware.webhooks import webhooks


async def worker_loop():
    queue = JobQueue()
    while True:
        job_id = await queue.redis.lpop("jobs:queue")
        if not job_id:
            await asyncio.sleep(1)
            continue
        await queue.set_status(job_id, "processing")
        # Placeholder processing. Hook to orchestrator in deployed runtime.
        result = {"job_id": job_id, "status": "completed", "processed": True}
        await queue.set_status(job_id, "completed", json.dumps(result))
        await webhooks.notify_all(result)


if __name__ == "__main__":
    asyncio.run(worker_loop())
