import uuid
from agent.tasks import TaskStatus, TaskState

from agent.tasks import ManagedTask, TaskSchedule
from agent.tasks import Repeat_Types

def create_skill_dev_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    dev_skill = next((sk for sk in agent_skills if sk.name == "test skill under development"), None)
    run_task = next((task for task in agent_tasks if task.name == "dev:run task for skill under development"), None)
    print("dev task dev_skill: ", dev_skill)
    if not run_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
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
        status = TaskStatus(state=TaskState.SUBMITTED)
        run_task = ManagedTask(
            id=task_id,
            name="dev:run task for skill under development",
            description="a holder for the skill under development.",
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


