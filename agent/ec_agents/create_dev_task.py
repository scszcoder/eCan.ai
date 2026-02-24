import uuid
from a2a.types import TaskStatus, TaskState
from agent.ec_tasks import ManagedTask, TaskSchedule, RepeatType
from utils.logger_helper import logger_helper as logger

def create_skill_dev_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    dev_skill = next((sk for sk in agent_skills if sk.name == "test skill under development"), None)
    run_task = next((task for task in agent_tasks if task.name == "dev:run task for skill under development"), None)
    logger.debug(f"dev task dev_skill: {dev_skill}")

    # Auto-create a minimal dev skill if one doesn't exist yet
    if dev_skill is None:
        from agent.ec_skill import EC_Skill
        dev_skill = EC_Skill(
            name="test skill under development",
            description="test run on a skill under development.",
            source="code",
        )
        agent_skills.append(dev_skill)
        logger.info(f"dev task dev_skill auto-created: {dev_skill}")
    if not run_task:
        task_schedule = TaskSchedule(
            repeat_type=RepeatType.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 23:59:59:000",
            end_date_time="2035-12-31 23:59:59:000",
            time_out=120  # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.submitted)
        run_task = ManagedTask(
            id=task_id,
            context_id=task_id,  # Required by a2a-sdk Task
            name="dev:run task for skill under development",
            description="a holder for the skill under development.",
            source="code",  # Mark as code-generated task
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=dev_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return run_task


