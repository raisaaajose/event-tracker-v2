from contextlib import asynccontextmanager
import os
import asyncio
from prisma import Prisma
from app.services.queue import start_worker, stop_worker

db = Prisma()


@asynccontextmanager
async def lifespan(app):
    await db.connect()
    await start_worker()

    scheduler_tasks: list[asyncio.Task] = []
    try:
        from app.services.email_sync import schedule_periodic_sync
        from app.services.queue import job_queue

        interval = int(os.getenv("EMAIL_SYNC_INTERVAL_SECONDS", "3600"))
        accounts = await db.googleaccount.find_many()
        for acc in accounts:
            await job_queue.put(
                {"type": "sync_inbox_once", "user_id": acc.userId, "max_results": 10}
            )

            task = asyncio.create_task(
                schedule_periodic_sync(
                    acc.userId, interval_seconds=interval, max_results=10
                )
            )
            scheduler_tasks.append(task)
    except Exception:
        pass
    try:
        yield
    finally:
        await stop_worker()

        for t in scheduler_tasks:
            t.cancel()
        if scheduler_tasks:
            try:
                await asyncio.gather(*scheduler_tasks, return_exceptions=True)
            except Exception:
                pass
        await db.disconnect()
