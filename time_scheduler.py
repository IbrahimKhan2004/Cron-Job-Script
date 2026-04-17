"""
time_scheduler.py — Timezone-aware daily scheduling
Handles user-selected specific times (e.g., 12 AM UTC, 11 AM IST)
"""

from datetime import datetime, time, timedelta, timezone
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Supported timezones
SUPPORTED_TIMEZONES = {
    "UTC": "UTC",
    "IST": "Asia/Kolkata",
}

# All hours: 0-23 (midnight to 11 PM)
AVAILABLE_HOURS = list(range(24))


def get_cron_trigger_for_time(hour: int, tz_name: str) -> CronTrigger:
    """
    Create a CronTrigger that fires at a specific hour in the given timezone.
    
    Args:
        hour: 0-23 (hour of day)
        tz_name: Timezone name ('UTC' or 'IST')
    
    Returns:
        CronTrigger that fires at hour:00 every day in the specified timezone
    """
    tz = pytz.timezone(SUPPORTED_TIMEZONES[tz_name])
    return CronTrigger(hour=hour, minute=0, second=0, timezone=tz)


def schedule_daily_job(
    scheduler: AsyncIOScheduler,
    job_id: str,
    run_func,
    hour: int,
    tz_name: str,
    job_args: list = None,
) -> None:
    """
    Schedule a daily job at a specific time in a specific timezone.
    
    Args:
        scheduler: APScheduler AsyncIOScheduler instance
        job_id: Unique job ID
        run_func: Async function to execute
        hour: 0-23 (hour of day)
        tz_name: 'UTC' or 'IST'
        job_args: Optional args list for run_func
    """
    if job_args is None:
        job_args = []
    
    trigger = get_cron_trigger_for_time(hour, tz_name)
    scheduler.add_job(
        run_func,
        trigger=trigger,
        id=job_id,
        args=job_args,
        replace_existing=True,
    )


def unschedule_daily_job(scheduler: AsyncIOScheduler, job_id: str) -> None:
    """Remove a daily scheduled job."""
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass


def get_next_run_time_for_daily(hour: int, tz_name: str) -> datetime:
    """
    Calculate next run time for a daily job at given hour/timezone.
    
    Returns:
        datetime object in the specified timezone
    """
    tz = pytz.timezone(SUPPORTED_TIMEZONES[tz_name])
    now = datetime.now(tz)
    target_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    
    # If target time has already passed today, next run is tomorrow
    if target_time <= now:
        target_time += timedelta(days=1)
    
    return target_time
