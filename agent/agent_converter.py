"""
Agent Converter Utility

Provides common functions to convert agent data (dict) to EC_Agent objects.
Used by both MainGUI and IPC handlers to ensure consistency.
"""

import json
import uuid
import traceback
from typing import Dict, Any, Optional, TYPE_CHECKING

from agent.ec_agent import EC_Agent
from agent.ec_skill import EC_Skill
from agent.ec_tasks.models import ManagedTask, TaskSchedule, RepeatType
from a2a.types import AgentCapabilities
from agent.a2a.langgraph_agent.utils import AgentCard, SUPPORTED_CONTENT_TYPES, get_a2a_server_url
from utils.logger_helper import logger_helper as logger
from agent.db.services.db_avatar_service import DBAvatarService

if TYPE_CHECKING:
    from gui.MainGUI import MainWindow


def _convert_dict_to_skill(skill_dict: Dict[str, Any]) -> EC_Skill:
    """
    Convert skill dictionary to EC_Skill object.
    
    Args:
        skill_dict: Skill data dictionary from database
        
    Returns:
        EC_Skill object
    """
    try:
        # Parse JSON strings for list/dict fields
        tags = skill_dict.get('tags')
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = None
        
        examples = skill_dict.get('examples')
        if isinstance(examples, str):
            try:
                examples = json.loads(examples)
            except (json.JSONDecodeError, TypeError):
                examples = None
        
        return EC_Skill(
            id=skill_dict.get('id'),
            name=skill_dict.get('name', 'Unnamed Skill'),
            description=skill_dict.get('description', ''),
            source=skill_dict.get('source', 'ui'),
            owner=skill_dict.get('owner', ''),
            version=skill_dict.get('version', '0.0.0'),
            level=skill_dict.get('level', 'entry'),
            path=skill_dict.get('path', ''),
            run_mode=skill_dict.get('run_mode', 'released'),
            # Optional fields
            tags=tags,
            examples=examples,
        )
    except Exception as e:
        logger.error(f"[AgentConverter] Failed to convert skill dict to object: {e}")
        # Return a minimal skill object
        return EC_Skill(
            name=skill_dict.get('name', 'Error Skill'),
            description=f"Failed to load: {e}"
        )


def _parse_schedule_from_dict(schedule_dict: Optional[Dict[str, Any]]) -> Optional[TaskSchedule]:
    """Parse schedule data from a task dict into a TaskSchedule object."""
    if not schedule_dict or not isinstance(schedule_dict, dict):
        return None
    try:
        from datetime import datetime, timedelta

        repeat_type_str = (schedule_dict.get("repeat_type") or "none").lower().strip()
        repeat_type_map = {
            "none": RepeatType.NONE,
            "seconds": RepeatType.BY_SECONDS, "by_seconds": RepeatType.BY_SECONDS, "by seconds": RepeatType.BY_SECONDS,
            "minutes": RepeatType.BY_MINUTES, "by_minutes": RepeatType.BY_MINUTES, "by minutes": RepeatType.BY_MINUTES,
            "hours": RepeatType.BY_HOURS, "by_hours": RepeatType.BY_HOURS, "by hours": RepeatType.BY_HOURS,
            "days": RepeatType.BY_DAYS, "by_days": RepeatType.BY_DAYS, "by days": RepeatType.BY_DAYS,
            "weeks": RepeatType.BY_WEEKS, "by_weeks": RepeatType.BY_WEEKS, "by weeks": RepeatType.BY_WEEKS,
            "months": RepeatType.BY_MONTHS, "by_months": RepeatType.BY_MONTHS, "by months": RepeatType.BY_MONTHS,
            "years": RepeatType.BY_YEARS, "by_years": RepeatType.BY_YEARS, "by years": RepeatType.BY_YEARS,
        }
        repeat_type = repeat_type_map.get(repeat_type_str, RepeatType.NONE)
        if repeat_type == RepeatType.NONE:
            return None  # No recurring schedule

        repeat_number = int(schedule_dict.get("repeat_number", 1))

        fmt = "%Y-%m-%d %H:%M:%S:%f"
        fmt_alt = "%Y-%m-%d %H:%M:%S"

        def _normalize_dt(dt_str, default_dt):
            if not dt_str:
                return default_dt.strftime(fmt)[:-3] + "000"
            for f in (fmt, fmt_alt):
                try:
                    return datetime.strptime(dt_str, f).strftime(fmt)[:-3] + "000"
                except ValueError:
                    pass
            try:
                dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
                # Convert to local time before stripping tzinfo so naive datetime
                # matches datetime.now() comparisons in the scheduler.
                if dt.tzinfo is not None:
                    dt = dt.astimezone().replace(tzinfo=None)
                else:
                    dt = dt.replace(tzinfo=None)
                return dt.strftime(fmt)[:-3] + "000"
            except Exception:
                return default_dt.strftime(fmt)[:-3] + "000"

        now = datetime.now()
        default_end = now + timedelta(days=365 * 10)
        start_dt = _normalize_dt(schedule_dict.get("start_date_time"), now)
        end_dt = _normalize_dt(schedule_dict.get("end_date_time"), default_end)
        time_out = int(schedule_dict.get("time_out", 120))

        return TaskSchedule(
            repeat_type=repeat_type,
            repeat_number=repeat_number,
            repeat_unit=repeat_type_str,
            start_date_time=start_dt,
            end_date_time=end_dt,
            time_out=time_out,
        )
    except Exception as e:
        logger.warning(f"[AgentConverter] Failed to parse schedule: {e}")
        return None


def _convert_dict_to_task(task_dict: Dict[str, Any]) -> ManagedTask:
    """
    Convert task dictionary to ManagedTask object.
    
    Args:
        task_dict: Task data dictionary from database
        
    Returns:
        ManagedTask object
    """
    from a2a.types import TaskStatus, TaskState
    
    try:
        # Create required status object
        status = TaskStatus(state=TaskState.submitted)
        
        # Extract skill info from task_dict (set during deep=True to_dict).
        # `skills`     — list of full skill dicts (populated only when the
        #                SQLAlchemy backref assoc.skill resolves to a non-None
        #                object).
        # `skill_ids`  — list of just the skill IDs from the rel column
        #                (always populated whenever the rel row exists,
        #                regardless of whether the skill object lazy-loads).
        #
        # The 2026-05-18 flood-test regression had `skill_ids=[skill_bd00…]`
        # but `skills=[]` — so the stub was created with no binding, the
        # compiled-pool resolution dropped any in-memory binding, and the
        # front-desk recipient_filter (skill_keywords=['rt_chat']) matched
        # zero agents.  Falling back to `skill_ids` here lets
        # _find_matching_skill_for_task's skill_id exact-match path
        # re-resolve `rt_chat_bot00` against the global compiled pool.
        task_skill = None
        skills_list = task_dict.get('skills', [])
        if skills_list and len(skills_list) > 0:
            # Take the first skill (primary skill)
            skill_dict = skills_list[0]
            if isinstance(skill_dict, dict) and 'name' in skill_dict:
                # Create a minimal skill object with name and id for later resolution
                task_skill = type('SkillStub', (), {
                    'name': skill_dict.get('name', ''),
                    'id': skill_dict.get('id', ''),
                    'runnable': None
                })()
        if task_skill is None:
            skill_ids = task_dict.get('skill_ids') or []
            if skill_ids:
                first_sid = str(skill_ids[0] or '').strip()
                if first_sid:
                    task_skill = type('SkillStub', (), {
                        'name': '',
                        'id': first_sid,
                        'runnable': None,
                    })()
        
        # Pass all fields to ManagedTask, let Pydantic validators handle conversion
        # Invalid values will be normalized by field_validator
        task_id = task_dict.get('id', str(uuid.uuid4()))
        schedule = _parse_schedule_from_dict(task_dict.get('schedule'))
        task_obj = ManagedTask(
            id=task_id,
            context_id=task_id,  # Required by a2a-sdk Task
            name=task_dict.get('name', 'Unnamed Task'),
            description=task_dict.get('description', ''),
            source=task_dict.get('source', 'ui'),
            status=status,
            priority=task_dict.get('priority'),  # Validator will handle 'none' -> None
            trigger=task_dict.get('trigger') or [],  # field_validator normalizes str/list/None
            agent_id=task_dict.get('agent_id') or '',
            schedule=schedule,
        )
        
        # Set skill if found in task_dict
        if task_skill:
            task_obj.skill = task_skill
        
        return task_obj
    except Exception as e:
        logger.error(f"[AgentConverter] Failed to convert task dict to object: {e}")
        # Return a minimal task object with required fields
        try:
            status = TaskStatus(state=TaskState.submitted)
            fallback_id = str(uuid.uuid4())
            return ManagedTask(
                id=fallback_id,
                context_id=fallback_id,  # Required by a2a-sdk Task
                name=task_dict.get('name', 'Error Task'),
                description=f"Failed to load: {e}",
                status=status,
            )
        except Exception as e2:
            logger.error(f"[AgentConverter] Failed to create fallback task: {e2}")
            raise


def _validate_and_filter_entities(data_list, entity_type, agent_id, agent_name):
    """
    Validate and filter entity data (skills/tasks).
    
    Filters out:
    - Relationship objects (have agent_id + skill_id/task_id but no name)
    - Invalid objects (missing name field)
    - Non-dict items
    
    Logs errors when relationship objects are detected.
    
    Args:
        data_list: List of entity dictionaries
        entity_type: 'skill' or 'task' for logging
        agent_id: Agent ID for error reporting
        agent_name: Agent name for error reporting
        
    Returns:
        List of valid entity objects with 'name' field
    """
    if not data_list:
        return []
    
    valid_entities = []
    
    for idx, item in enumerate(data_list):
        # Skip non-dict items with detailed error
        if not isinstance(item, dict):
            logger.error(
                f"[AgentConverter] ❌ Invalid {entity_type} type at index {idx}\n"
                f"  Agent: {agent_name} ({agent_id})\n"
                f"  Expected: dict (object with fields)\n"
                f"  Got: {type(item).__name__}\n"
                f"  Value: {repr(item)[:200]}\n"
                f"  Hint: Check DBAgent.to_dict(deep=True) - should return list of dicts, not list of strings/IDs"
            )
            continue
        
        # Detect relationship object: has agent_id and skill_id/task_id but no name
        entity_id_field = f"{entity_type}_id"
        is_relationship = (
            'agent_id' in item and 
            entity_id_field in item and 
            'name' not in item
        )
        
        if is_relationship:
            # Log error: relationship object should not be here
            logger.error(
                f"[AgentConverter] ❌ Data format error: Relationship object in {entity_type}s data\n"
                f"  Agent: {agent_name} ({agent_id}), Index: {idx}\n"
                f"  Found: agent_id={item.get('agent_id')}, {entity_id_field}={item.get(entity_id_field)}\n"
                f"  Expected: Entity object with 'name' field\n"
                f"  Hint: Check DBAgent.to_dict() - should return entity objects, not relationship objects"
            )
            continue
        
        # Keep valid entity objects (have 'name' field)
        if 'name' in item:
            valid_entities.append(item)
        else:
            logger.error(
                f"[AgentConverter] ❌ Invalid {entity_type} at index {idx}: missing 'name' field\n"
                f"  Agent: {agent_name} ({agent_id})\n"
                f"  Item keys: {list(item.keys())}\n"
                f"  Item preview: {str(item)[:200]}\n"
                f"  Hint: Entity objects must have a 'name' field"
            )
    
    return valid_entities


def _resolve_from_compiled_pool(stubs, compiled_pool, entity_type, agent_name):
    """Replace stub objects with compiled versions from the global pool.
    
    Matches by ID first, then by name (case-insensitive).
    If no compiled match is found, keeps the stub.
    
    Args:
        stubs: List of stub EC_Skill or ManagedTask objects (no runnable)
        compiled_pool: List of compiled objects from mainwin.agent_skills or agent_tasks
        entity_type: 'skill' or 'task' for logging
        agent_name: Agent name for logging
        
    Returns:
        List of resolved objects (compiled where possible, stubs as fallback)
    """
    if not stubs:
        return []
    if not compiled_pool:
        logger.warning(f"[AgentConverter] No compiled {entity_type}s available for agent '{agent_name}' — using stubs")
        return stubs
    
    # Build lookup indices for the compiled pool
    by_id = {}
    by_name = {}
    for obj in compiled_pool:
        obj_id = getattr(obj, 'id', None)
        obj_name = (getattr(obj, 'name', '') or '').lower().strip()
        if obj_id:
            by_id[str(obj_id)] = obj
        if obj_name:
            by_name[obj_name] = obj
    
    resolved = []
    for stub in stubs:
        stub_id = str(getattr(stub, 'id', '') or '')
        stub_name = (getattr(stub, 'name', '') or '').lower().strip()
        
        # Match by ID first
        match = by_id.get(stub_id)
        # Then by name
        if not match:
            match = by_name.get(stub_name)
        
        if match:
            has_runnable = entity_type == 'skill' and getattr(match, 'runnable', None) is not None
            # Preserve per-agent skill binding from the DB stub onto the
            # shared compiled task.  The compiled task pool
            # (mainwin.agent_tasks) is built once at startup from the
            # global task list and carries no per-agent skill rel;
            # without this re-attach, _attach_skills_and_triggers later
            # sees task.skill=None / skill_name='' and fails to bind
            # rt_chat_bot00 to its live-chat skill — which then makes the
            # front-desk PreDispatch recipient filter (skill_keywords=
            # ['rt_chat']) match zero live agents and abort the entire
            # customer-message dispatch.  Logged 2026-05-18 flood-test
            # regression.
            if entity_type == 'task':
                stub_skill = getattr(stub, 'skill', None)
                match_skill = getattr(match, 'skill', None)
                if stub_skill and not match_skill:
                    try:
                        match.skill = stub_skill
                        logger.info(
                            f"[AgentConverter] 🔗 Preserved stub skill "
                            f"binding on compiled task "
                            f"'{getattr(stub, 'name', '?')}' → "
                            f"skill='{getattr(stub_skill, 'name', '?')}' "
                            f"(id={getattr(stub_skill, 'id', '?')})"
                        )
                    except Exception as _exc:
                        logger.warning(
                            f"[AgentConverter] Could not re-attach stub "
                            f"skill to compiled task "
                            f"'{getattr(stub, 'name', '?')}': "
                            f"{type(_exc).__name__}: {_exc}"
                        )
            logger.info(
                f"[AgentConverter] ✅ Resolved {entity_type} '{getattr(stub, 'name', '?')}' "
                f"for agent '{agent_name}' from compiled pool"
                f"{' (has runnable)' if has_runnable else ''}"
            )
            resolved.append(match)
        else:
            logger.warning(
                f"[AgentConverter] ⚠️ No compiled {entity_type} found for "
                f"'{getattr(stub, 'name', '?')}' (id={stub_id}) in agent '{agent_name}' — using stub"
            )
            resolved.append(stub)
    
    return resolved


def _find_matching_skill_for_task(task_obj, skill_objects, compiled_skills):
    """
    Find and attach a matching executable skill to a task.
    
    Matching priority:
    1. skill_id exact match (if task already has a skill_id bound)
    2. skill_name exact match
    3. skill_name contains match (prefix/suffix)
    4. task name contains skill name words
    
    Returns (matched_skill, old_skill_name) or (None, None) if no match found.
    """
    task_name_lower = (getattr(task_obj, 'name', '') or '').lower()
    
    task_skill = getattr(task_obj, 'skill', None)
    has_correct_skill = task_skill is not None and getattr(task_skill, 'runnable', None) is not None
    
    if has_correct_skill:
        logger.info(f"[AgentConverter] Task '{task_obj.name}' already has a valid skill attached")
        return None, None
    
    # Build search pools: agent's own skills first, then global compiled pool
    search_pools = []
    if skill_objects:
        search_pools.append(('agent_skills', skill_objects))
    if compiled_skills:
        search_pools.append(('global_pool', compiled_skills))
    
    if not search_pools:
        logger.warning(f"[AgentConverter] No search pools available for task '{task_obj.name}'")
        return None, None
    
    matched_skill = None
    skill_name_on_task = ''
    skill_id_on_task = ''
    
    # Extract skill info from task_skill
    if isinstance(task_skill, str):
        skill_name_on_task = task_skill.lower().strip()
    elif task_skill:
        skill_name_on_task = (getattr(task_skill, 'name', '') or '').lower().strip()
        skill_id_on_task = (getattr(task_skill, 'id', '') or '').strip()
    
    task_name_stripped = task_name_lower.strip()
    logger.info(f"[AgentConverter] Task '{task_obj.name}': skill_id='{skill_id_on_task}', skill_name='{skill_name_on_task}', task='{task_name_stripped}'")
    
    for pool_name, pool in search_pools:
        if matched_skill:
            break
        
        logger.debug(f"[AgentConverter] Searching pool '{pool_name}' ({len(pool)} items)")
        
        # 0. skill_id exact match (PRIORITY - if task has a bound skill_id)
        if skill_id_on_task:
            for sk in pool:
                sk_id = (getattr(sk, 'id', '') or '').strip()
                has_runnable = getattr(sk, 'runnable', None) is not None
                if sk_id and sk_id == skill_id_on_task and has_runnable:
                    matched_skill = sk
                    logger.info(f"[AgentConverter] Found skill_id match in '{pool_name}': id={sk_id}, name={getattr(sk, 'name', '?')}")
                    break
            if matched_skill:
                break
        
        # 1. Exact skill name match (require runnable)
        if not matched_skill and skill_name_on_task:
            matched_skill = next(
                (sk for sk in pool
                 if (getattr(sk, 'name', '') or '').lower().strip() == skill_name_on_task
                 and getattr(sk, 'runnable', None) is not None),
                None,
            )
            if matched_skill:
                logger.info(f"[AgentConverter] Found exact name match in '{pool_name}': {getattr(matched_skill, 'name', '?')}")
                break
        
        # 2. Substring match: task name contains skill name or vice versa (prefix match)
        if not matched_skill and task_name_stripped:
            best_match = None
            best_len = 0
            for sk in pool:
                sk_name = (getattr(sk, 'name', '') or '').lower().strip()
                has_runnable = getattr(sk, 'runnable', None) is not None
                if not sk_name:
                    continue
                # Match if task starts with skill or skill starts with task (prefix match)
                is_match = task_name_stripped.startswith(sk_name) or sk_name.startswith(task_name_stripped)
                logger.debug(f"[AgentConverter] Checking prefix match: task='{task_name_stripped}' vs skill='{sk_name}', match={is_match}, has_runnable={has_runnable}")
                if is_match and has_runnable:
                    if len(sk_name) > best_len:
                        best_match = sk
                        best_len = len(sk_name)
                        logger.debug(f"[AgentConverter] New best match: '{sk_name}' (len={best_len})")
            matched_skill = best_match
            if matched_skill:
                logger.info(f"[AgentConverter] Found prefix match in '{pool_name}': {getattr(matched_skill, 'name', '?')}")
        
        # 3. Contains match: task contains skill word or skill contains task word (for cases like "chat:product listing chatter task" matching "product_listing_orchestrator")
        if not matched_skill and task_name_stripped:
            best_match = None
            best_len = 0
            for sk in pool:
                sk_name = (getattr(sk, 'name', '') or '').lower().strip()
                has_runnable = getattr(sk, 'runnable', None) is not None
                if not sk_name or not has_runnable:
                    continue
                
                # Skip short common words that cause false positives
                skip_words = {'chat', 'task', 'the', 'a', 'an', 'and', 'or', 'for', 'to'}
                
                # Split names into words for better matching
                task_words = set(w for w in task_name_stripped.replace('_', ' ').split() if w not in skip_words and len(w) > 2)
                skill_words = set(w for w in sk_name.replace('_', ' ').split() if w not in skip_words and len(w) > 2)
                
                # Check if any significant word matches
                common_words = task_words & skill_words
                if common_words:
                    logger.debug(f"[AgentConverter] Found common words: {common_words} between task='{task_name_stripped}' and skill='{sk_name}'")
                    # Prefer skill name that has more common words or is longer
                    score = len(common_words) * 100 + len(sk_name)
                    if score > best_len:
                        best_match = sk
                        best_len = score
                        logger.debug(f"[AgentConverter] New contains match: '{sk_name}' (score={score}, common_words={common_words})")
            
            if best_match:
                matched_skill = best_match
                logger.info(f"[AgentConverter] Found contains match in '{pool_name}': {getattr(matched_skill, 'name', '?')}")
    
    old_skill_name = getattr(task_skill, 'name', 'None') if task_skill else 'None'
    if not matched_skill:
        logger.warning(f"[AgentConverter] No skill match found for task '{task_obj.name}'")
    return matched_skill, old_skill_name


def _attach_skills_and_triggers(task_objects, skill_objects, compiled_skills):
    """Attach executable skills to tasks and ensure chat tasks have message trigger."""
    logger.info(f"[AgentConverter] _attach_skills_and_triggers: {len(task_objects)} tasks, {len(skill_objects)} agent skills, {len(compiled_skills)} compiled skills")
    
    # Log compiled skills for debugging
    for idx, sk in enumerate(compiled_skills):
        sk_name = getattr(sk, 'name', '?') if sk else 'None'
        has_runnable = getattr(sk, 'runnable', None) is not None if sk else False
        logger.debug(f"[AgentConverter] Compiled skill[{idx}]: name={sk_name}, has_runnable={has_runnable}")
    
    for task_obj in task_objects:
        task_name = getattr(task_obj, 'name', '?')
        task_id = getattr(task_obj, 'id', '?')
        logger.info(f"[AgentConverter] Processing task: name={task_name}, id={task_id}")
        
        matched_skill, old_skill_name = _find_matching_skill_for_task(
            task_obj, skill_objects, compiled_skills
        )
        
        if matched_skill:
            task_obj.skill = matched_skill
            logger.info(
                f"[AgentConverter] Attached skill to task '{task_obj.name}': "
                f"'{old_skill_name}' → '{getattr(matched_skill, 'name', '?')}'"
            )
        else:
            task_name_lower = (getattr(task_obj, 'name', '') or '').lower()
            is_chat_task = 'chat' in task_name_lower
            task_skill = getattr(task_obj, 'skill', None)
            skill_name_on_task = getattr(task_skill, 'name', '') if task_skill else ''
            
            # Log available skills with runnable for debugging when matching fails
            available_skills = []
            for sk in (skill_objects or []):
                sk_name = getattr(sk, 'name', '?') if sk else 'None'
                has_runnable = getattr(sk, 'runnable', None) is not None if sk else False
                available_skills.append(f"{sk_name}(runnable={has_runnable})")
            for sk in (compiled_skills or []):
                sk_name = getattr(sk, 'name', '?') if sk else 'None'
                has_runnable = getattr(sk, 'runnable', None) is not None if sk else False
                available_skills.append(f"{sk_name}(runnable={has_runnable})")
            
            logger.warning(
                f"[AgentConverter] ❌ No skill matched for task '{task_obj.name}' "
                f"(task_skill='{skill_name_on_task}', is_chat={is_chat_task}). "
                f"Available skills: {available_skills if available_skills else 'None'}"
            )
        
        # Ensure chat tasks have 'message' trigger
        task_name_lower = (getattr(task_obj, 'name', '') or '').lower()
        if 'chat' in task_name_lower:
            triggers = getattr(task_obj, 'trigger', []) or []
            if 'message' not in triggers:
                triggers = list(triggers) + ['message']
                task_obj.trigger = triggers
                logger.info(f"[AgentConverter] Added 'message' trigger to chat task '{task_obj.name}' → {triggers}")


def convert_agent_dict_to_ec_agent(
    agent_data: Dict[str, Any],
    main_window: 'MainWindow'
) -> Optional[EC_Agent]:
    """
    Convert agent data (dict) to EC_Agent object.
    
    This is the standard conversion logic used across the application
    to ensure consistency between MainGUI and IPC handlers.
    
    Args:
        agent_data: Agent data dictionary from database
        main_window: MainWindow instance for accessing llm and other resources
        
    Returns:
        EC_Agent object or None if conversion fails
    """
    try:
        agent_name = agent_data.get('name', 'Unknown')
        agent_id = agent_data.get('id', 'Unknown')
        skills_data_preview = agent_data.get('skills') or []
        tasks_data_preview = agent_data.get('tasks') or []
        compiled_skills_count = len(getattr(main_window, 'agent_skills', None) or [])
        compiled_tasks_count = len(getattr(main_window, 'agent_tasks', None) or [])
        logger.info(
            f"[AgentConverter] Converting agent '{agent_name}' (id={agent_id}): "
            f"skills_data={len(skills_data_preview)}, tasks_data={len(tasks_data_preview)}, "
            f"compiled_skills_pool={compiled_skills_count}, compiled_tasks_pool={compiled_tasks_count}"
        )
        
        # Create capabilities
        capabilities_data = agent_data.get('capabilities')
        if isinstance(capabilities_data, dict):
            capabilities = AgentCapabilities(**capabilities_data)
        else:
            capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        
        # Create AgentCard
        card = AgentCard(
            id=agent_data.get('id', str(uuid.uuid4())),
            name=agent_data.get('name', 'Unknown Agent'),
            description=agent_data.get('description') or '',
            url=agent_data.get('url') or get_a2a_server_url(main_window),
            version=agent_data.get('version') or '1.0.0',
            capabilities=capabilities,
            default_input_modes=agent_data.get('default_input_modes') or SUPPORTED_CONTENT_TYPES,
            default_output_modes=agent_data.get('default_output_modes') or SUPPORTED_CONTENT_TYPES,
            skills=[]  # DB agents don't have skills initially
        )
        
        # Get org_id (single value)
        org_id = agent_data.get('org_id')
        
        # Parse extra_data if it's a JSON string
        extra_data = agent_data.get('extra_data') or {}
        if isinstance(extra_data, str):
            try:
                extra_data = json.loads(extra_data) if extra_data else {}
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"[AgentConverter] Failed to parse extra_data JSON: {extra_data}")
                extra_data = {}
        elif not isinstance(extra_data, dict):
            extra_data = {}
        
        # Create browser_use compatible LLM from main_window configuration (no fallback)
        from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm
        browser_use_llm = create_browser_use_llm(mainwin=main_window, skip_playwright_check=True)
        if not browser_use_llm:
            raise ValueError("Failed to create browser_use LLM from main_window. Please configure LLM provider API key in Settings.")
        
        avatar = agent_data.get('avatar') or DBAvatarService.generate_default_avatar(agent_data.get('id'))
        
        # Extract relationship data from agent_data
        # IMPORTANT: Database returns relationship objects (dicts), but EC_Agent expects:
        # - skills: EC_Skill objects (not implemented yet, so keep empty)
        # - tasks: ManagedTask objects (not implemented yet, so keep empty)
        # These relationship data are stored separately for frontend display via to_dict()
        skills_data = agent_data.get('skills') or []
        tasks_data = agent_data.get('tasks') or []
        title = agent_data.get('title') or ''
        if isinstance(title, str) and title.startswith('['):
            try:
                title = json.loads(title)
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Parse personalities if it's a JSON string
        personalities = agent_data.get('personalities') or []
        if isinstance(personalities, str) and personalities.startswith('['):
            try:
                personalities = json.loads(personalities)
            except (json.JSONDecodeError, ValueError):
                personalities = []
        
        main_window_llm = getattr(main_window, 'llm', None)
        
        ec_agent = EC_Agent(
            mainwin=main_window,
            skill_llm=main_window_llm,
            llm=browser_use_llm or main_window_llm,
            task="",  # Required by parent Agent class
            tasks=[],  # Will be set after validation and conversion
            skills=[],  # Will be set after validation and conversion
            card=card,
            supervisor_id=agent_data.get('supervisor_id'),
            rank=agent_data.get('rank', 'member'),
            org_id=org_id,
            title=title,
            gender=agent_data.get('gender', 'male'),
            birthday=agent_data.get('birthday'),
            personalities=personalities,
            vehicle=agent_data.get('vehicle_id'),  # 只使用标准字段
            avatar=avatar
        )
        
        # Store additional fields that might not be in __init__ but needed for serialization
        ec_agent.owner = agent_data.get('owner')
        ec_agent.description = agent_data.get('description') or ''
        ec_agent.status = agent_data.get('status') or 'active'
        ec_agent.vehicle_id = agent_data.get('vehicle_id')  # 只使用标准字段
        ec_agent.extra_data = agent_data.get('extra_data', '')
        
        # ✅ Validate, filter, and convert skills/tasks data to objects
        # Detects relationship objects and logs errors
        filtered_skills_dicts = _validate_and_filter_entities(
            skills_data, 'skill', agent_data.get('id'), agent_data.get('name')
        )
        filtered_tasks_dicts = _validate_and_filter_entities(
            tasks_data, 'task', agent_data.get('id'), agent_data.get('name')
        )
        
        # Convert dictionaries to stub objects
        skill_stubs = [_convert_dict_to_skill(s) for s in filtered_skills_dicts]
        task_stubs = [_convert_dict_to_task(t) for t in filtered_tasks_dicts]
        
        # ✅ Replace stubs with compiled versions from mainwin.agent_skills / agent_tasks
        # DB-loaded stubs have no runnable; the compiled pool does.
        compiled_skills = getattr(main_window, 'agent_skills', None) or []
        compiled_tasks = getattr(main_window, 'agent_tasks', None) or []

        skill_objects = _resolve_from_compiled_pool(
            skill_stubs, compiled_skills, 'skill', agent_data.get('name')
        )
        task_objects = _resolve_from_compiled_pool(
            task_stubs, compiled_tasks, 'task', agent_data.get('name')
        )

        # Skill attachment and trigger adjustment for tasks
        _attach_skills_and_triggers(task_objects, skill_objects, compiled_skills)
        
        # Update EC_Agent with resolved objects
        ec_agent.skills = skill_objects
        ec_agent.tasks = task_objects
        
        logger.debug(f"[AgentConverter] ✅ Converted agent: {agent_data.get('name')}, org_id: {ec_agent.org_id}")
        return ec_agent
        
    except Exception as e:
        logger.error(f"[AgentConverter] ❌ Failed to convert agent {agent_data.get('name')}: {e}")
        logger.error(f"[AgentConverter] Traceback: {traceback.format_exc()}")
        return None
