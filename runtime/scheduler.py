from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from runtime.queue import Job, JobQueue
from runtime.resource_manager import ResourceManager

JobHandler = Callable[[Job], dict[str, Any]]


class LocalScheduler:
    def __init__(self, queue: JobQueue, resources: ResourceManager) -> None:
        self.queue = queue
        self.resources = resources

    def run(self, handler: JobHandler) -> dict[str, Job]:
        claimed: list[Job] = []
        while (job := self.queue.claim()) is not None:
            claimed.append(job)
        with ThreadPoolExecutor(max_workers=len(claimed) or 1) as executor:
            futures = [executor.submit(self._execute, job, handler) for job in claimed]
            for future in futures:
                future.result()
        return {job.job_id: job for job in claimed}

    def _execute(self, job: Job, handler: JobHandler) -> None:
        self.resources.acquire()
        try:
            self.queue.succeed(job.job_id, handler(job))
        except Exception as exc:
            self.queue.fail(job.job_id, str(exc))
        finally:
            self.resources.release()
