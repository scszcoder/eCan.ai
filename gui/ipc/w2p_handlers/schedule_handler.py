import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from datetime import datetime, timedelta
from app_context import AppContext
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger


def _calculate_next_execution_time(start_time_str: str, end_time_str: str, 
                                   repeat_type: str, repeat_number: int, 
                                   last_run_time: Optional[datetime],
                                   is_running: bool = False) -> tuple:
    """
    Calculate execution status and metadata for a task.
    
    IMPORTANT: This function does NOT modify the start/end times!
    It only determines the execution status and whether it's a long-period task.
    The frontend is responsible for splitting long tasks into daily events.
    
    Returns:
        tuple: (start_time_str, end_time_str, is_long_period, execution_status)
    """
    try:
        # Parse times
        start_time = datetime.strptime(start_time_str.split(':')[0] + ':' + start_time_str.split(':')[1] + ':' + start_time_str.split(':')[2], 
                                      "%Y-%m-%d %H:%M:%S")
        end_time = datetime.strptime(end_time_str.split(':')[0] + ':' + end_time_str.split(':')[1] + ':' + end_time_str.split(':')[2], 
                                    "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        
        # Check if it's a long-period task (duration > 1 day)
        duration = end_time - start_time
        is_long_period = duration.days > 1
        
        # Determine execution status
        if is_running:
            status = 'running'
        elif now < start_time:
            status = 'pending'  # Not started yet
        elif now > end_time:
            status = 'completed'  # Already finished
        elif start_time <= now <= end_time:
            status = 'running'  # Currently in progress
        else:
            status = 'scheduled'
        
        # ALWAYS return original times - let frontend handle the display
        return start_time_str, end_time_str, is_long_period, status
        
    except Exception as e:
        logger.warning(f"Failed to calculate execution status: {e}")
        return start_time_str, end_time_str, False, 'error'


@IPCHandlerRegistry.handler('get_schedules')
def handle_get_schedules(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get Schedule handler called with request: {request}")

        main_window = AppContext.get_main_window()
        agents = main_window.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)

        # Build schedules with task information
        # Deduplication strategy:
        # 1. For recurring tasks (BY_DAYS, BY_WEEKS, etc.), only keep ONE schedule per task name
        # 2. For one-time tasks (NONE), keep all unique schedules
        # 3. Filter out invalid schedules (same start/end time or empty dates)
        schedules_with_task_info = []
        # Dictionaries to track seen tasks
        seen_recurring_tasks = {}  # task_name -> (schedule_data, last_run_time)
        seen_onetime_keys = set()  # (task_name, start_time, end_time)
        
        logger.info(f"📊 Processing {len(all_tasks)} tasks for deduplication...")  # 添加任务处理开始日志
        
        invalid_schedules = []  # Track invalid schedules for logging
        
        for task in all_tasks:
            if task.schedule:
                schedule_data = task.schedule.model_dump(mode='json')
                start_time = schedule_data.get('start_date_time', '')
                end_time = schedule_data.get('end_date_time', '')
                repeat_type = schedule_data.get('repeat_type', 'NONE')
                
                # Validate schedule data
                # Note: start_time == end_time is VALID for long-running tasks (e.g., chat tasks)
                # Only filter out if dates are truly empty
                if not start_time or not end_time:
                    # Invalid schedule: log and skip
                    invalid_schedules.append({
                        'taskId': task.id,
                        'taskName': task.name,
                        'startTime': start_time,
                        'endTime': end_time,
                        'reason': 'empty_dates'
                    })
                    logger.warning(f"⚠️  Invalid schedule filtered: task='{task.name}' (id={task.id}), "
                                 f"start='{start_time}', end='{end_time}' - SKIPPED (empty dates)")
                    continue
                
                # Add task information to schedule
                schedule_data['taskId'] = task.id
                schedule_data['taskName'] = task.name
                schedule_data['taskDescription'] = task.description
                
                # Add execution history information
                last_run_time = None
                if hasattr(task, 'last_run_datetime') and task.last_run_datetime:
                    schedule_data['lastRunDateTime'] = task.last_run_datetime.isoformat()
                    last_run_time = task.last_run_datetime
                if hasattr(task, 'already_run_flag'):
                    schedule_data['alreadyRun'] = task.already_run_flag
                
                # Check if task is currently running
                is_running = False
                if hasattr(task, 'status') and task.status:
                    task_state = getattr(task.status, 'state', None)
                    is_running = task_state in ['RUNNING', 'EXECUTING', 'IN_PROGRESS']
                
                # Calculate next execution time for recurring tasks
                repeat_number = schedule_data.get('repeat_number', 1)
                next_start, next_end, is_long_period, exec_status = _calculate_next_execution_time(
                    start_time, end_time, repeat_type, repeat_number, last_run_time, is_running
                )
                
                # Update schedule times to next execution
                schedule_data['executionStatus'] = exec_status  # running, scheduled, completed, pending, error
                if next_start != start_time or next_end != end_time:
                    schedule_data['start_date_time'] = next_start
                    schedule_data['end_date_time'] = next_end
                    schedule_data['isNextExecution'] = True  # Flag to indicate this is calculated
                    if is_long_period:
                        schedule_data['isLongPeriod'] = True
                        schedule_data['originalEndTime'] = end_time  # Keep original end time for reference
                
                # Handle recurring tasks - only keep the most recent one
                if repeat_type and repeat_type != 'NONE':
                    if task.name in seen_recurring_tasks:
                        # Compare with existing entry - keep the one with more recent last_run_time
                        existing_data, existing_last_run = seen_recurring_tasks[task.name]
                        if last_run_time and existing_last_run:
                            if last_run_time > existing_last_run:
                                # Replace with newer one
                                seen_recurring_tasks[task.name] = (schedule_data, last_run_time)
                                logger.debug(f"🔄 Updated recurring task: '{task.name}' with newer execution")
                        # If no last_run_time info, keep the first one
                    else:
                        # First occurrence of this recurring task
                        seen_recurring_tasks[task.name] = (schedule_data, last_run_time)
                else:
                    # One-time task - use traditional deduplication
                    schedule_key = (task.name, start_time, end_time)
                    if schedule_key not in seen_onetime_keys:
                        schedules_with_task_info.append(schedule_data)
                        seen_onetime_keys.add(schedule_key)
                    else:
                        logger.debug(f"🔄 Duplicate one-time schedule skipped: task='{task.name}'")
        
        # Add all recurring tasks to the result
        logger.info(f"📊 Deduplication results:")
        logger.info(f"  - Recurring tasks (unique by name): {len(seen_recurring_tasks)}")
        logger.info(f"  - One-time tasks (unique by name+time): {len(seen_onetime_keys)}")
        logger.info(f"  - Total tasks after deduplication: {len(seen_recurring_tasks) + len(seen_onetime_keys)}")
        
        for task_name, (schedule_data, _) in seen_recurring_tasks.items():
            schedules_with_task_info.append(schedule_data)
            logger.debug(f"  ✅ Recurring: {task_name}")
        
        # Log summary of invalid schedules
        if invalid_schedules:
            logger.warning(f"🗑️  Filtered {len(invalid_schedules)} invalid schedule(s). "
                         f"Please clean up these tasks from database:")
            for inv in invalid_schedules:
                logger.warning(f"   - Task: {inv['taskName']} (ID: {inv['taskId']}) - Reason: {inv['reason']}")

        resultJS = {
            'schedules': schedules_with_task_info,
            'message': 'Get all successful'
        }
        logger.info(f'📅 Returning {len(schedules_with_task_info)} schedules to frontend')
        logger.debug(f'📅 Schedule summary:')
        for schedule in schedules_with_task_info[:5]:  # Log first 5 for debugging
            logger.debug(f"  - {schedule.get('taskName')}: {schedule.get('start_date_time')} -> {schedule.get('end_date_time')} [{schedule.get('executionStatus')}]")
        if len(schedules_with_task_info) > 5:
            logger.debug(f"  ... and {len(schedules_with_task_info) - 5} more")
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get schedules handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get schedules: {str(e)}"
        )