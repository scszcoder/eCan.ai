import traceback
import typing
import uuid
import asyncio
from agent.ec_agents.agent_utils import load_agent_tasks_from_cloud
from agent.a2a.common.types import TaskStatus, TaskState
from agent.ec_tasks import ManagedTask, TaskSchedule, RepeatType

from utils.logger_helper import logger_helper as logger
from agent.ec_agents.create_dev_task import create_skill_dev_task
if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow


def _generate_stable_task_id(name: str, source: str) -> str:
    """Generate a stable ID for code tasks based on name, or random UUID for ui tasks.
    
    Code-generated tasks use 'code-task-' prefix for easy identification.
    """
    if source == "code":
        # Use uuid5 with a namespace to generate deterministic ID from name
        namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace for names
        uuid_part = str(uuid.uuid5(namespace, f"code-task:{name}"))
        return f"code-task-{uuid_part}"  # Add prefix to identify code-generated tasks
    return str(uuid.uuid4())


def _get_or_create_task(
    mainwin: 'MainWindow',
    skill_matcher: typing.Union[str, typing.Callable],
    task_name: str,
    description: str,
    trigger: str = "message",
    schedule_kwargs: dict = None,
    state: dict = None,
    task_id: str = None
) -> typing.Optional[ManagedTask]:
    """Generic helper to get or create an agent task based on skill and task name."""
    try:
        agent_skills = getattr(mainwin, "agent_skills", [])
        agent_tasks = getattr(mainwin, "agent_tasks", [])

        # 1. Find Skill
        if not agent_skills:
            logger.error(f"[_get_or_create_task] agent_skills is empty or None! Cannot create task '{task_name}'.")
            return None
        
        if isinstance(skill_matcher, str):
            skill = next((sk for sk in agent_skills if getattr(sk, "name", "") == skill_matcher), None)
        else:
            skill = next((sk for sk in agent_skills if skill_matcher(sk)), None)

        if skill is None:
            matcher_desc = skill_matcher if isinstance(skill_matcher, str) else "custom_matcher"
            logger.warning(f"[_get_or_create_task] Cannot find skill '{matcher_desc}' for task '{task_name}', task will be created without skill")
            # Log available skills for debugging
            available_skills = [getattr(sk, "name", "UNKNOWN") for sk in agent_skills]
            logger.debug(f"[_get_or_create_task] Available skills: {available_skills}")
            # Continue to create task without skill (original behavior)

        # 2. Find Existing Task
        existing_task = None
        if agent_tasks:
            existing_task = next((task for task in agent_tasks if getattr(task, "name", "") == task_name), None)

        if existing_task:
            # Update existing task logic
            updated = False
            if existing_task.skill is None:
                existing_task.skill = skill
                updated = True
                logger.info(f"[_get_or_create_task] ✅ Updated existing task '{task_name}' with skill '{skill.name}'")
            
            # Ensure metadata/state
            if not hasattr(existing_task, 'metadata') or existing_task.metadata is None:
                default_state = state or {"top": "ready"}
                existing_task.metadata = {"state": default_state}
                existing_task.state = default_state
                updated = True
                logger.info(f"[_get_or_create_task] ✅ Updated existing task '{task_name}' with default metadata")

            if updated:
                 logger.info(f"[_get_or_create_task] Task '{task_name}' updated successfully")
            
            return existing_task

        # 3. Create New Task
        # Default schedule if not provided
        default_schedule = {
            "repeat_type": RepeatType.NONE,
            "repeat_number": 1,
            "repeat_unit": "day",
            "start_date_time": "2025-03-31 23:59:59:000",
            "end_date_time": "2035-12-31 23:59:59:000",
            "time_out": 120
        }
        
        if schedule_kwargs:
            default_schedule.update(schedule_kwargs)
            
        task_schedule = TaskSchedule(**default_schedule)
        
        task_state = state or {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        
        # Generate stable ID for code-generated task
        task_id_final = task_id if task_id else _generate_stable_task_id(task_name, "code")
        
        new_task = ManagedTask(
            id=task_id_final,
            name=task_name,
            description=description,
            source="code",  # Mark as code-generated task
            status=status,
            sessionId="",
            skill=skill,
            metadata={"state": task_state},
            state=task_state,
            resume_from="",
            trigger=trigger,
            schedule=task_schedule
        )
        
        logger.info(f"[_get_or_create_task] Created new task: {new_task.name}, id: {new_task.id}")
        return new_task
        
    except Exception as e:
        logger.error(f"[_get_or_create_task] Exception while creating task '{task_name}': {e}")
        logger.error(traceback.format_exc())
        return None


def create_my_twin_chat_task(mainwin: 'MainWindow'):
    return _get_or_create_task(
        mainwin,
        skill_matcher="chatter for my digital twin",
        task_name="chat:Human Chatter Relay Task",
        description="Represent human to chat with others",
        trigger="interaction"
    )


def create_ec_helper_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="chatter for ecbot rpa helper",
        task_name="chat:ECBot RPA Helper Chatter Task",
        description="chat with human about anything related to helper work.",
        trigger="message"
    )

def create_ec_helper_work_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa helper",
        task_name="work:ECBot RPA Helper Task",
        description="Help fix errors/failures during e-commerce RPA run",
        trigger="schedule"
    )


def create_ec_customer_support_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa customer support internal chatter",
        task_name="chat:ECBot RPA Customer Support Internal Chatter Task",
        description="chat with human user about anything related to customer support work.",
        trigger="message",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )

def create_ec_customer_support_work_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa customer support",
        task_name="work:eCan.ai After Sales Customer Support Work",
        description="eCan.ai After Sales Support Work like shipping prep, customer Q&A, handle return, refund, resend, etc.",
        trigger="schedule",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )


def create_ec_marketing_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa marketing chatter",
        task_name="chat:eCan.ai Marketing Chatter Task",
        description="chat with human user about anything related to e-commerce marketing work.",
        trigger="message",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )

def create_ec_marketing_work_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa marketing",
        task_name="work:E-Commerce Marketing Work",
        description="Help fix errors/failures during e-commerce RPA run",
        trigger="schedule",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )

def create_ec_procurement_chat_task(mainwin):
    # Special schedule for procurement
    schedule_kwargs = {
        "repeat_type": RepeatType.BY_DAYS,
        "start_date_time": "2025-03-31 01:00:00:000",
        "end_date_time": "2035-12-31 01:30:00:000",
        "time_out": 1800
    }
    return _get_or_create_task(
        mainwin,
        skill_matcher="search_digikey_chatter",
        task_name="chat:eCan.ai Procurement Chatter Task",
        description="chat with human user about anything related to e-commerce procurement work.",
        trigger="interaction",
        schedule_kwargs=schedule_kwargs
    )

def create_ec_procurement_work_task(mainwin):
    # Custom matcher for skill: should match 'search_digikey_chatter' or similar
    # Original matcher was too strict ("search parts" and no "chatter")
    def skill_matcher(sk):
        # return "search parts" in sk.name and "chatter" not in sk.name
        # Allow chatter skill to double as worker skill if needed, or match specific worker skill
        return "search" in sk.name and "digikey" in sk.name
        
    schedule_kwargs = {
        "repeat_type": RepeatType.BY_DAYS,
        "start_date_time": "2025-03-31 01:00:00:000",
        "end_date_time": "2035-12-31 01:30:00:000",
        "time_out": 1800
    }
    return _get_or_create_task(
        mainwin,
        skill_matcher=skill_matcher,
        task_name="work:E-Commerce Part Procurement Task",
        description="Help sourcing products/parts for product development",
        trigger="message",
        schedule_kwargs=schedule_kwargs
    )

def create_ec_rpa_operator_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="chatter for ecbot rpa operator run RPA",
        task_name="chat:ECBot RPA Operator Chatter Task",
        description="chat with human user about anything related to ECBOT RPA work.",
        trigger="message"
    )

def create_ec_rpa_operator_work_task(mainwin):
    # Custom matcher for skill: "ecbot rpa operator run RPA" in name
    def skill_matcher(sk):
        return "ecbot rpa operator run RPA" in sk.name
        
    return _get_or_create_task(
        mainwin,
        skill_matcher=skill_matcher,
        task_name="work:ECBot RPA operates daily routine task",
        description="Help fix errors/failures during e-commerce RPA run",
        trigger="schedule"
    )


def create_ec_rpa_supervisor_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="chatter for ecbot rpa supervisor task scheduling",
        task_name="chat:eCan.ai RPA Operator Chatter Task",
        description="chat with human user about anything related to ECBOT RPA work.",
        trigger="message"
    )

def create_ec_rpa_supervisor_daily_task(mainwin):
    # Special schedule for daily supervisor task
    schedule_kwargs = {
        "repeat_type": RepeatType.BY_DAYS,
        "start_date_time": "2025-03-31 03:00:00:000",
        "end_date_time": "2035-12-31 23:59:59:000"
    }
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa supervisor task scheduling",
        task_name="work:eCan.ai RPA Supervise Daily Routine Task",
        description="Do any routine like fetch todays work schedule, prepare operators team and dispatch work to the operators to do.",
        trigger="schedule",
        schedule_kwargs=schedule_kwargs
    )

def create_ec_rpa_supervisor_on_request_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa supervisor serve requests",
        task_name="work:eCan.ai RPA Supervisor Service Task",
        description="Serve RPA operators in case they request human in loop or work reports",
        trigger="schedule"
    )


def create_ec_sales_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa sales internal chatter",
        task_name="chat:eCan.ai Sales Chatter Task",
        description="chat with human user about anything related to e-commerce sales work.",
        trigger="message",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )

def create_ec_sales_work_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="ecbot rpa sales",
        task_name="work:ECBot Sales",
        description="Help fix errors/failures during e-commerce RPA run",
        trigger="schedule",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )


def create_ec_self_tester_chat_task(mainwin):
    return _get_or_create_task(
        mainwin,
        skill_matcher="self_test_chatter",
        task_name="chat:eCan.ai Self Test Chatter Task",
        description="chat with human user about anything related to eCan.ai self test work.",
        trigger="message",
        schedule_kwargs={"repeat_type": RepeatType.BY_DAYS}
    )

def create_ec_self_tester_work_task(mainwin):
    # Special schedule for self tester
    schedule_kwargs = {
        "repeat_type": RepeatType.BY_DAYS,
        "start_date_time": "2025-03-31 01:59:59:000",
        "end_date_time": "2035-12-31 01:59:59:000"
    }
    return _get_or_create_task(
        mainwin,
        skill_matcher="eCan.ai self test",
        task_name="work:eCan.ai Self Test",
        description="eCan.ai app software self test",
        trigger="message",
        schedule_kwargs=schedule_kwargs
    )



def _convert_db_agent_task_to_object(db_agent_task_dict):
    """Convert database agent task dictionary to ManagedTask object"""
    try:
        # Create agent task status
        status = TaskStatus(state=TaskState.SUBMITTED)

        # Create agent task schedule if available
        schedule_data = db_agent_task_dict.get('schedule', {})
        if schedule_data:
            # Handle None values for date fields - convert to empty string
            start_date = schedule_data.get('start_date_time')
            end_date = schedule_data.get('end_date_time')
            
            schedule = TaskSchedule(
                repeat_type=getattr(RepeatType, schedule_data.get('repeat_type', 'NONE'), RepeatType.NONE),
                repeat_number=schedule_data.get('repeat_number', 1),
                repeat_unit=schedule_data.get('repeat_unit', 'day'),
                start_date_time=start_date if start_date is not None else '',
                end_date_time=end_date if end_date is not None else '',
                time_out=schedule_data.get('time_out', 120)
            )
        else:
            schedule = None

        # Handle priority field - map 'none' to 'low' (valid Priority_Types value)
        # Valid values: 'low', 'mid', 'High', 'Urgent', 'ASAP'
        priority_value = db_agent_task_dict.get('priority', 'mid')
        if priority_value == 'none' or priority_value == 'medium':
            priority_value = 'mid'  # Map 'none' and 'medium' to 'mid'
        
        # Create ManagedTask object (agent task)
        # Note: ManagedTask is a Pydantic model, we can only set fields that are defined in the model
        agent_task = ManagedTask(
            id=db_agent_task_dict.get('id', f"agent_task_{uuid.uuid4().hex[:16]}"),
            name=db_agent_task_dict.get('name', 'Unnamed Agent Task'),
            description=db_agent_task_dict.get('description', ''),
            source=db_agent_task_dict.get('source', 'ui'),  # Preserve source from database
            owner=db_agent_task_dict.get('owner', ''),
            status=status,
            sessionId='',
            skill=None,
            schedule=schedule,
            resumeFrom='',
            state={},
            trigger=db_agent_task_dict.get('trigger', 'manual'),
            priority=priority_value
        )

        # Note: task_type, objectives, progress, result, error_message, settings are not fields in ManagedTask
        # They are stored in the database but not needed for the ManagedTask object
        
        return agent_task

    except Exception as e:
        logger.error(f"Failed to convert DB agent task to object: {e}")
        return None


async def _load_agent_tasks_from_database_async(main_win):
    """Async load agent tasks from database"""
    try:
        logger.info("[create_agent_tasks] Loading from database...")

        # Get database service from mainwin
        if not (main_win and hasattr(main_win, 'ec_db_mgr')):
            logger.warning("[create_agent_tasks] ec_db_mgr not available")
            return []

        agent_task_service = main_win.ec_db_mgr.task_service
        # Use main_win.user (original username like 249511118@qq.com) not log_user (sanitized like 249511118_qq_com)
        username = getattr(main_win, 'user', 'default_user')
        logger.info(f"[create_agent_tasks] Loading agent tasks for user: {username}")

        # Run database query in executor to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, agent_task_service.query_tasks, None, None)

        if not result.get('success'):
            logger.error(f"[create_agent_tasks] Query failed: {result.get('error')}")
            return []

        db_agent_tasks_data = result.get('data', [])
        logger.info(f"[create_agent_tasks] Found {len(db_agent_tasks_data)} total agent tasks in database")

        # Convert to ManagedTask objects and filter by owner
        db_agent_tasks = []
        filtered_count = 0
        for agent_task_dict in db_agent_tasks_data:
            task_owner = agent_task_dict.get('owner')
            task_name = agent_task_dict.get('name', 'Unknown')
            
            if task_owner == username:
                agent_task_obj = _convert_db_agent_task_to_object(agent_task_dict)
                if agent_task_obj:
                    db_agent_tasks.append(agent_task_obj)
                    logger.info(f"[create_agent_tasks] ✅ Loaded task: {task_name} (owner: {task_owner})")
                else:
                    logger.warning(f"[create_agent_tasks] ⚠️ Failed to convert task: {task_name}")
            else:
                filtered_count += 1
                logger.debug(f"[create_agent_tasks] ⏭️ Skipped task (owner mismatch): {task_name} (owner: {task_owner} != {username})")

        logger.info(f"[create_agent_tasks] Loaded {len(db_agent_tasks)} agent tasks for user {username}")
        logger.info(f"[create_agent_tasks] Filtered out {filtered_count} tasks (owner mismatch)")
        return db_agent_tasks

    except Exception as e:
        logger.error(f"[create_agent_tasks] Error: {e}")
        return []


async def _load_agent_tasks_from_cloud_async(main_win):
    """Async load agent tasks from cloud"""
    try:
        logger.info("[create_agent_tasks] Loading from cloud...")

        # Run cloud loading in executor to avoid blocking
        loop = asyncio.get_event_loop()
        cloud_agent_tasks = await loop.run_in_executor(None, load_agent_tasks_from_cloud, main_win)

        logger.info(f"[create_agent_tasks] Loaded {len(cloud_agent_tasks or [])} agent tasks")
        return cloud_agent_tasks or []

    except Exception as e:
        logger.error(f"[create_agent_tasks] Error: {e}")
        return []


async def _build_local_agent_tasks_async(main_win):
    """Async build local code agent tasks (currently disabled)"""
    try:
        logger.info("[create_agent_tasks] Building local agent tasks...")

        # Currently disabled - local agent tasks are commented out
        # In the future, this will be removed entirely
        local_agent_tasks = []
        # for now just build a few agents.
        local_agent_tasks.append(create_my_twin_chat_task(main_win))
        local_agent_tasks.append(create_ec_helper_chat_task(main_win))
        local_agent_tasks.append(create_ec_helper_work_task(main_win))
        # local_agent_tasks.append(create_ec_customer_support_chat_task(main_win))
        # local_agent_tasks.append(create_ec_customer_support_work_task(main_win))
        local_agent_tasks.append(create_ec_procurement_chat_task(main_win))
        local_agent_tasks.append(create_ec_procurement_work_task(main_win))
        local_agent_tasks.append(create_ec_rpa_operator_chat_task(main_win))
        local_agent_tasks.append(create_ec_rpa_operator_work_task(main_win))
        local_agent_tasks.append(create_ec_rpa_supervisor_chat_task(main_win))
        local_agent_tasks.append(create_ec_rpa_supervisor_daily_task(main_win))
        local_agent_tasks.append(create_ec_rpa_supervisor_on_request_task(main_win))
        local_agent_tasks.append(create_ec_self_tester_chat_task(main_win))
        local_agent_tasks.append(create_ec_self_tester_work_task(main_win))
        local_agent_tasks.append(create_skill_dev_task(main_win))
        # local_agent_tasks.append(create_ec_sales_chat_task(main_win))
        # local_agent_tasks.append(create_ec_sales_work_task(main_win))

        logger.info(f"[create_agent_tasks] Built {len(local_agent_tasks)} local agent tasks")
        return local_agent_tasks

    except Exception as e:
        logger.error(f"[create_agent_tasks] Error: {e}")
        return []


async def _update_database_with_cloud_agent_tasks(cloud_agent_tasks, main_win):
    """Async update database with cloud agent tasks (background task)"""
    try:
        logger.info(f"[create_agent_tasks] Updating {len(cloud_agent_tasks)} agent tasks...")

        # TODO: Implement database update logic
        # This should save cloud agent tasks to local database

        logger.info("[create_agent_tasks] Update completed")

    except Exception as e:
        logger.error(f"[create_agent_tasks] Error: {e}")


async def build_agent_tasks(main_win):
    """Build Agent Tasks - supports local database + cloud data + local code triple data sources

    Data flow (similar to build_agent_skills):
    1. Parallel loading: local database + cloud data
    2. Wait for both to complete, cloud data takes priority and overwrites local database
    3. Add locally built agent tasks from code
    4. Update mainwindow.agent_tasks memory
    5. TODO: After agents are built, merge agent.tasks into mainwin.agent_tasks
       (This step will be deprecated in the future)
    """
    try:
        logger.info("[build_agent_tasks] Starting agent task building with DB+Cloud+Local integration...")

        # Step 1: Parallel loading from local database and cloud
        logger.info("[build_agent_tasks] Step 1: Parallel loading DB and Cloud...")
        db_task = asyncio.create_task(_load_agent_tasks_from_database_async(main_win))
        cloud_task = asyncio.create_task(_load_agent_tasks_from_cloud_async(main_win))

        # Step 2: Wait for both database and cloud to complete
        logger.info("[build_agent_tasks] Step 2: Waiting for DB and Cloud...")
        db_agent_tasks = []
        cloud_agent_tasks = []

        try:
            db_agent_tasks = await asyncio.wait_for(db_task, timeout=5.0)
            logger.info(f"[build_agent_tasks] ✅ Loaded {len(db_agent_tasks)} agent tasks from database")
        except asyncio.TimeoutError:
            logger.warning("[build_agent_tasks] ⏰ Database timeout")
        except Exception as e:
            logger.error(f"[build_agent_tasks] ❌ Database failed: {e}")

        try:
            cloud_agent_tasks = await asyncio.wait_for(cloud_task, timeout=10.0)
            logger.info(f"[build_agent_tasks] ✅ Loaded {len(cloud_agent_tasks or [])} agent tasks from cloud")
        except asyncio.TimeoutError:
            logger.warning("[build_agent_tasks] ⏰ Cloud timeout")
        except Exception as e:
            logger.error(f"[build_agent_tasks] ❌ Cloud failed: {e}")

        # Step 3: Check cloud data, if available overwrite local database
        final_db_agent_tasks = []
        if cloud_agent_tasks and len(cloud_agent_tasks) > 0:
            logger.info(f"[build_agent_tasks] Step 3: Cloud data available, using cloud agent tasks...")

            # Cloud data overwrites local database (background async execution, non-blocking)
            asyncio.create_task(_update_database_with_cloud_agent_tasks(cloud_agent_tasks, main_win))
            logger.info(f"[build_agent_tasks] 🔄 Database update started in background (non-blocking)")

            # Use cloud data as final database agent tasks
            final_db_agent_tasks = cloud_agent_tasks
            logger.info(f"[build_agent_tasks] ✅ Using {len(cloud_agent_tasks)} cloud agent tasks")
        else:
            # No cloud data, use local database data
            logger.info(f"[build_agent_tasks] Step 3: No cloud data, using database agent tasks...")
            final_db_agent_tasks = db_agent_tasks

        # Step 4: Build local code agent tasks
        local_agent_tasks = []
        logger.info("[build_agent_tasks] Step 4: Building local code agent tasks...")
        try:
            local_agent_tasks = await _build_local_agent_tasks_async(main_win)
            logger.info(f"[build_agent_tasks] Built {len(local_agent_tasks or [])} local code agent tasks")
        except Exception as e:
            logger.error(f"[build_agent_tasks] Local build failed: {e}")
            local_agent_tasks = []

        # Step 5: Merge all agent tasks (code-generated tasks override DB tasks)
        logger.info("[build_agent_tasks] Step 5: Merging all agent tasks...")
        
        # Create a dict to store tasks by name for deduplication
        task_dict = {}
        
        # First add DB tasks
        for task in final_db_agent_tasks:
            if task is not None:
                task_dict[task.name] = task
        
        # Then add code-generated tasks (will override DB tasks with same name)
        if local_agent_tasks:
            for task in local_agent_tasks:
                if task is not None:
                    if task.name in task_dict:
                        logger.info(f"[build_agent_tasks] Code-generated task '{task.name}' overrides DB task")
                    task_dict[task.name] = task
        
        # Convert back to list
        all_agent_tasks = list(task_dict.values())

        # Step 6: Update mainwindow.agent_tasks memory
        logger.info("[build_agent_tasks] Step 6: Updating mainwindow.agent_tasks...")
        main_win.agent_tasks = all_agent_tasks

        # Log final results
        agent_task_names = [t.name for t in all_agent_tasks] if all_agent_tasks else []
        logger.info(f"[build_agent_tasks] 🎉 Complete! Total: {len(all_agent_tasks)} agent tasks")
        logger.info(f"[build_agent_tasks] - DB/Cloud agent tasks: {len(final_db_agent_tasks)}")
        logger.info(f"[build_agent_tasks] - Local code agent tasks: {len(local_agent_tasks or [])}")
        logger.info(f"[build_agent_tasks] - Agent task names: {agent_task_names}")

        # TODO: Step 7 will be added after agents are built
        # Merge agent.tasks from built agents into mainwin.agent_tasks
        # This step will be deprecated in the future

        return all_agent_tasks

    except Exception as e:
        logger.error(f"[build_agent_tasks] Error: {e}")
        logger.error(f"[build_agent_tasks] Traceback: {traceback.format_exc()}")
        return []






