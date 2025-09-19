import asyncio
from typing import Any, Callable, Dict


job_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
_worker_task: asyncio.Task | None = None


async def start_worker() -> None:
    global _worker_task

    async def _worker() -> None:
        from app.services.email_sync import handle_job

        while True:
            job = await job_queue.get()
            try:
                await handle_job(job)
            except Exception:
                pass
            finally:
                job_queue.task_done()

    _worker_task = asyncio.create_task(_worker())


async def stop_worker() -> None:
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except Exception:
            pass
        _worker_task = None
