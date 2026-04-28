"""Background job execution for audit runs."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import Any

from config.logging_config import logger
from config.settings import settings
from pipeline.runner import PipelineRunner
from service.storage import RunStore


class JobManager:
    """Executes audits in background threads and tracks active futures."""

    def __init__(self, store: RunStore, max_workers: int = 4) -> None:
        self.store = store
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: dict[int, Future] = {}
        self._lock = Lock()

    def submit_run(self, payload: dict[str, Any]) -> int:
        run_id = self.store.create_run(payload["url"], payload)
        future = self._executor.submit(self._execute_run, run_id, payload)
        with self._lock:
            self._futures[run_id] = future
        return run_id

    def _execute_run(self, run_id: int, payload: dict[str, Any]) -> None:
        self.store.mark_running(run_id)
        original_format = settings.report_format
        original_ai = settings.run_ai_analysis
        original_seo = settings.run_seo
        original_perf = settings.run_performance
        try:
            settings.report_format = payload["format"]
            settings.run_ai_analysis = not payload["no_ai"]
            settings.run_seo = not payload["no_seo"]
            settings.run_performance = not payload["no_perf"]
            settings.validate_runtime(payload["url"], payload["max_pages"])

            result = PipelineRunner(
                url=payload["url"],
                max_pages=payload["max_pages"],
            ).run_with_details()
            self.store.mark_completed(run_id, result)
        except Exception as exc:  # pragma: no cover - safety net
            logger.exception("Background run failed")
            self.store.mark_failed(run_id, str(exc))
        finally:
            settings.report_format = original_format
            settings.run_ai_analysis = original_ai
            settings.run_seo = original_seo
            settings.run_performance = original_perf
            with self._lock:
                self._futures.pop(run_id, None)
