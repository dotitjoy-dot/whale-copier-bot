"""
APScheduler async wrapper for managing background jobs.
Provides a thin layer over AsyncIOScheduler for add/remove/start/stop.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from core.logger import get_logger

logger = get_logger(__name__)


class Scheduler:
    """
    Async APScheduler wrapper.
    Manages all background polling jobs for the whale tracker and monitors.
    """

    def __init__(self) -> None:
        """Initialize the AsyncIOScheduler with UTC timezone."""
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def add_interval_job(
        self,
        func: Callable,
        seconds: int,
        job_id: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
        replace_existing: bool = True,
    ) -> None:
        """
        Add or replace an interval-based job.

        Args:
            func: Async callable to run.
            seconds: Interval in seconds between executions.
            job_id: Unique identifier for this job.
            args: Positional arguments to pass to func.
            kwargs: Keyword arguments to pass to func.
            replace_existing: If True, replaces a job with the same id.
        """
        self._scheduler.add_job(
            func,
            trigger=IntervalTrigger(seconds=seconds),
            id=job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=replace_existing,
            max_instances=1,
            coalesce=True,
        )
        logger.debug("Scheduled interval job '%s' every %ds", job_id, seconds)

    def add_cron_job(
        self,
        func: Callable,
        hour: int,
        minute: int,
        job_id: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
    ) -> None:
        """
        Add a daily cron-style job.

        Args:
            func: Async callable to run.
            hour: Hour of day (UTC) to run.
            minute: Minute of hour to run.
            job_id: Unique identifier for this job.
            args: Positional arguments to pass to func.
            kwargs: Keyword arguments to pass to func.
        """
        self._scheduler.add_job(
            func,
            trigger=CronTrigger(hour=hour, minute=minute),
            id=job_id,
            args=args or [],
            kwargs=kwargs or {},
            replace_existing=True,
        )
        logger.debug("Scheduled cron job '%s' at %02d:%02d UTC", job_id, hour, minute)

    def remove_job(self, job_id: str) -> None:
        """
        Remove a scheduled job by id. Silently ignores missing jobs.

        Args:
            job_id: Job identifier to remove.
        """
        try:
            self._scheduler.remove_job(job_id)
            logger.debug("Removed job '%s'", job_id)
        except Exception:
            pass  # Job may not exist

    def start(self) -> None:
        """Start the scheduler (non-blocking)."""
        self._scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self, wait: bool = False) -> None:
        """
        Stop the scheduler.

        Args:
            wait: If True, wait for all running jobs to complete.
        """
        self._scheduler.shutdown(wait=wait)
        logger.info("Scheduler shut down")

    @property
    def running(self) -> bool:
        """Return True if the scheduler is currently running."""
        return self._scheduler.running
