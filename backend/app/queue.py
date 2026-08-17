"""In-process work queue.

A thread pool over a bounded queue, sized by WORKER_CONCURRENCY. This keeps the
judge's setup to a single container while still giving real batch parallelism —
the pipeline is IO-bound on the vision API, so threads are the right tool.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path

from . import db
from .config import settings
from .models import DesignMetadata
from .pipeline import fetcher, run

log = logging.getLogger(__name__)


@dataclass
class Task:
    design_id: str
    job_id: str
    filename: str
    source: str
    source_ref: str | None
    path: Path | None  # None => fetch source_ref first
    meta: DesignMetadata


_q: queue.Queue[Task | None] = queue.Queue()
_workers: list[threading.Thread] = []
_started = threading.Event()


def submit(task: Task) -> None:
    _q.put(task)


def pending() -> int:
    return _q.qsize()


def _handle(task: Task) -> None:
    db.mark_design_running(task.design_id)
    try:
        path = task.path
        if path is None:
            if not task.source_ref:
                raise RuntimeError("No file and no URL to fetch")
            path, _ = fetcher.fetch(task.source_ref)

        report = run.analyze_design(
            design_id=task.design_id,
            path=path,
            filename=task.filename,
            source=task.source,
            source_ref=task.source_ref,
            meta=task.meta,
        )
        db.save_report(task.design_id, report.model_dump(mode="json"))
        db.bump_job(task.job_id, ok=True)

    except Exception as exc:
        log.exception("Analysis failed for %s (%s)", task.design_id, task.filename)
        report = run.failed_report(
            design_id=task.design_id,
            filename=task.filename,
            source=task.source,
            source_ref=task.source_ref,
            meta=task.meta,
            error=str(exc),
        )
        db.save_report(task.design_id, report.model_dump(mode="json"))
        db.save_design_error(task.design_id, str(exc))
        db.bump_job(task.job_id, ok=False)


def _loop() -> None:
    while True:
        task = _q.get()
        try:
            if task is None:
                return
            _handle(task)
        finally:
            _q.task_done()


def start() -> None:
    if _started.is_set():
        return
    _started.set()
    for i in range(max(1, settings.worker_concurrency)):
        t = threading.Thread(target=_loop, name=f"worker-{i}", daemon=True)
        t.start()
        _workers.append(t)
    log.info("Started %d analysis workers", len(_workers))


def stop() -> None:
    for _ in _workers:
        _q.put(None)
