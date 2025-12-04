"""
Task Scheduler - Schedule calculation and time-based task management.

This module handles all scheduling logic including:
- Next runtime calculation
- Repeat interval computation
- Time-to-run checks
"""

from datetime import datetime, timedelta
from calendar import monthrange
from typing import List, Optional, Tuple, TYPE_CHECKING

from utils.logger_helper import logger_helper as logger

from .models import TaskSchedule, RepeatType

if TYPE_CHECKING:
    from .models import ManagedTask


# ==================== Date/Time Helpers ====================

def add_months(dt: datetime, months: int) -> datetime:
    """Add months to a datetime, handling month-end edge cases."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def add_years(dt: datetime, years: int) -> datetime:
    """Add years to a datetime, handling leap year edge cases."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # Handle Feb 29 -> Feb 28 on non-leap years
        return dt.replace(month=2, day=28, year=dt.year + years)


# ==================== Schedule Calculations ====================

def get_next_runtime(schedule: TaskSchedule) -> Tuple[datetime, bool]:
    """
    Calculate the next runtime for a scheduled task.
    
    Args:
        schedule: The task schedule configuration.
        
    Returns:
        Tuple of (next_runtime, should_run_now)
    """
    fmt = "%Y-%m-%d %H:%M:%S:%f"
    now = datetime.now()
    
    logger.debug(f"Checking start time: {schedule.start_date_time}")
    start_time = datetime.strptime(schedule.start_date_time, fmt)
    end_time = datetime.strptime(schedule.end_date_time, fmt)
    repeat_number = int(schedule.repeat_number)
    
    if schedule.repeat_type == RepeatType.NONE:
        return start_time, False  # Never auto-run
    
    # Calculate next runtime based on repeat type
    next_runtime = _calculate_next_runtime(
        schedule.repeat_type, 
        repeat_number, 
        start_time, 
        now
    )
    
    # Clamp to end_time
    if next_runtime > end_time:
        next_runtime = end_time
    
    should_run_now = now >= next_runtime
    return next_runtime, should_run_now


def _calculate_next_runtime(
    repeat_type: RepeatType,
    repeat_number: int,
    start_time: datetime,
    now: datetime
) -> datetime:
    """Calculate next runtime based on repeat type."""
    
    if repeat_type == RepeatType.BY_SECONDS:
        delta = timedelta(seconds=repeat_number)
    elif repeat_type == RepeatType.BY_MINUTES:
        delta = timedelta(minutes=repeat_number)
    elif repeat_type == RepeatType.BY_HOURS:
        delta = timedelta(hours=repeat_number)
    elif repeat_type == RepeatType.BY_DAYS:
        logger.debug(f"Checking daily schedule: {repeat_number}")
        delta = timedelta(days=repeat_number)
    elif repeat_type == RepeatType.BY_WEEKS:
        delta = timedelta(weeks=repeat_number)
    elif repeat_type == RepeatType.BY_MONTHS:
        next_runtime = start_time
        while next_runtime <= now:
            next_runtime = add_months(next_runtime, repeat_number)
        return next_runtime
    elif repeat_type == RepeatType.BY_YEARS:
        next_runtime = start_time
        while next_runtime <= now:
            next_runtime = add_years(next_runtime, repeat_number)
        return next_runtime
    else:
        raise ValueError(f"Unsupported repeat type: {repeat_type}")
    
    # For time-delta based schedules
    elapsed = (now - start_time).total_seconds()
    intervals = max(0, int(elapsed // delta.total_seconds()))
    return start_time + delta * (intervals + 1)


def get_runtime_bounds(schedule: TaskSchedule) -> Tuple[datetime, datetime]:
    """
    Get the last and next runtime bounds for a schedule.
    
    Args:
        schedule: The task schedule configuration.
        
    Returns:
        Tuple of (last_runtime, next_runtime)
    """
    fmt = "%Y-%m-%d %H:%M:%S:%f"
    now = datetime.now()
    start_time = datetime.strptime(schedule.start_date_time, fmt)
    end_time = datetime.strptime(schedule.end_date_time, fmt)
    repeat_number = int(schedule.repeat_number)
    
    if schedule.repeat_type == RepeatType.NONE:
        return start_time, start_time  # One-time tasks
    
    last_runtime, next_runtime = _calculate_runtime_bounds(
        schedule.repeat_type,
        repeat_number,
        start_time,
        now
    )
    
    # Clamp to end time
    if next_runtime > end_time:
        next_runtime = end_time
    if last_runtime > end_time:
        last_runtime = end_time
    
    return last_runtime, next_runtime


def _calculate_runtime_bounds(
    repeat_type: RepeatType,
    repeat_number: int,
    start_time: datetime,
    now: datetime
) -> Tuple[datetime, datetime]:
    """Calculate last and next runtime bounds."""
    
    # Time-delta based schedules
    unit_seconds = {
        RepeatType.BY_SECONDS: 1,
        RepeatType.BY_MINUTES: 60,
        RepeatType.BY_HOURS: 3600,
        RepeatType.BY_DAYS: 86400,
        RepeatType.BY_WEEKS: 7 * 86400,
    }
    
    if repeat_type in unit_seconds:
        delta_seconds = unit_seconds[repeat_type] * repeat_number
        elapsed = (now - start_time).total_seconds()
        intervals = max(0, int(elapsed // delta_seconds))
        last_runtime = start_time + timedelta(seconds=delta_seconds * intervals)
        next_runtime = last_runtime + timedelta(seconds=delta_seconds)
        return last_runtime, next_runtime
    
    # Month-based schedule
    if repeat_type == RepeatType.BY_MONTHS:
        last_runtime = start_time
        while last_runtime <= now:
            future = add_months(last_runtime, repeat_number)
            if future > now:
                return last_runtime, future
            last_runtime = future
        return last_runtime, add_months(last_runtime, repeat_number)
    
    # Year-based schedule
    if repeat_type == RepeatType.BY_YEARS:
        last_runtime = start_time
        while last_runtime <= now:
            future = add_years(last_runtime, repeat_number)
            if future > now:
                return last_runtime, future
            last_runtime = future
        return last_runtime, add_years(last_runtime, repeat_number)
    
    raise ValueError(f"Unsupported repeat type: {repeat_type}")


def get_repeat_interval_seconds(schedule: TaskSchedule) -> int:
    """
    Get the repeat interval in seconds.
    
    Args:
        schedule: The task schedule configuration.
        
    Returns:
        Interval in seconds.
    """
    repeat_number = schedule.repeat_number
    
    intervals = {
        RepeatType.BY_SECONDS: 1,
        RepeatType.BY_MINUTES: 60,
        RepeatType.BY_HOURS: 3600,
        RepeatType.BY_DAYS: 86400,
        RepeatType.BY_WEEKS: 7 * 86400,
        RepeatType.BY_MONTHS: 30 * 86400,  # Rough average
        RepeatType.BY_YEARS: 365 * 86400,
    }
    
    if schedule.repeat_type in intervals:
        return repeat_number * intervals[schedule.repeat_type]
    
    raise ValueError(f"Unsupported repeat type: {schedule.repeat_type}")


# ==================== Task Selection ====================

def find_tasks_ready_to_run(tasks: List["ManagedTask"]) -> Optional["ManagedTask"]:
    """
    Find the next scheduled task that should run now.
    
    Sorts tasks by overdue time and returns the most overdue task.
    
    Args:
        tasks: List of managed tasks to check.
        
    Returns:
        The task to run, or None if no task is ready.
    """
    candidates = []
    now = datetime.now()
    
    for task in tasks:
        # Skip tasks without schedule or non-time-based tasks
        if not task.schedule:
            continue
        if task.schedule.repeat_type == RepeatType.NONE:
            continue
        if task.trigger != "schedule":
            continue
        
        last_runtime, next_runtime = get_runtime_bounds(task.schedule)
        
        # Calculate elapsed time since last task run
        if task.last_run_datetime:
            elapsed_since_last_run = (now - task.last_run_datetime).total_seconds()
        else:
            elapsed_since_last_run = float('inf')  # Never ran before
        
        repeat_seconds = get_repeat_interval_seconds(task.schedule)
        overdue_time = (now - last_runtime).total_seconds()
        
        logger.debug(f"overdue: {overdue_time}, repeat: {repeat_seconds}, elapsed: {elapsed_since_last_run}")
        
        # Should we run now?
        if (now >= last_runtime and
            elapsed_since_last_run > repeat_seconds / 2 and
            not task.already_run_flag):
            candidates.append({
                "overdue": overdue_time,
                "task": task
            })
        
        # Reset already_run_flag if now is close to the next scheduled run time
        if abs((next_runtime - now).total_seconds()) <= 30 * 60:
            task.already_run_flag = False
    
    if not candidates:
        return None
    
    # Sort tasks: run the most overdue task first
    candidates.sort(key=lambda x: x["overdue"], reverse=True)
    
    selected_task = candidates[0]["task"]
    selected_task.last_run_datetime = now
    selected_task.already_run_flag = True
    
    return selected_task
