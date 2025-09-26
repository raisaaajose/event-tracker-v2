import asyncio
from typing import Any, Dict


job_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
_worker_task: asyncio.Task | None = None

_SHUTDOWN_SENTINEL_KEY = "_shutdown"


async def start_worker() -> None:
    """Start the background worker that consumes jobs from job_queue.

    Uses a sentinel message to terminate gracefully instead of task cancellation
    so that platform (e.g. Render) shutdowns don't surface CancelledError in logs.
    """
    global _worker_task

    async def _worker() -> None:
        from app.services.email_sync import handle_job

        try:
            while True:
                job: Dict[str, Any] = await job_queue.get()
                try:
                    if job.get(_SHUTDOWN_SENTINEL_KEY):
                        job_queue.task_done()
                        break
                    await handle_job(job)
                except Exception:
                    pass
                finally:
                    if not job.get(_SHUTDOWN_SENTINEL_KEY):
                        job_queue.task_done()
        except asyncio.CancelledError:
            pass

    _worker_task = asyncio.create_task(_worker(), name="job-queue-worker")


async def stop_worker() -> None:
    """Signal the worker to stop and wait for it to finish gracefully."""
    global _worker_task
    if _worker_task:
        await job_queue.put({_SHUTDOWN_SENTINEL_KEY: True})
        try:
            await _worker_task
        finally:
            _worker_task = None
