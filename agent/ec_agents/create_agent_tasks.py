from agent.ec_skill import *
from agent.ec_agents.agent_utils import load_agent_tasks_from_cloud
from agent.a2a.common.types import TaskStatus, TaskState

from agent.tasks import TaskRunner, ManagedTask, TaskSchedule
from agent.tasks import Repeat_Types

from utils.logger_helper import logger_helper as logger



def create_my_twin_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks
    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for my digital twin"), None)
    chat_task = next((task for task in agent_tasks if task.name == "Human Chatter Task"), None)

    if not chat_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        chat_task = ManagedTask(
            id=task_id,
            name="Human Chatter Task",
            description="Represent human to chat with others",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="interaction",
            schedule=task_schedule
        )

    return chat_task


def create_ec_helper_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks
    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa helper"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "ECBot RPA Helper Chatter Task"), None)

    if not chatter_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        chatter_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Chatter Task",
            description="chat with human about anything related to helper work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return chatter_task

def create_ec_helper_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    worker_task = next((task for task in agent_tasks if task.name == "ECBot RPA Helper Task"), None)

    if not worker_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Helper Task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )

    return worker_task


def create_ec_customer_support_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa customer support internal chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "ECBot RPA Customer Support Internal Chatter Task"), None)

    if not chatter_task:
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
        chatter_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Customer Support Internal Chatter Task",
            description="chat with human user about anything related to customer support work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return chatter_task

def create_ec_customer_support_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa customer support"), None)
    worker_task = next((task for task in agent_tasks if task.name == "MECA After Sales Customer Support Work"), None)

    if not worker_task:
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
        worker_task = ManagedTask(
            id=task_id,
            name="MECA After Sales Customer Support Work",
            description="MECA After Sales Support Work like shipping prep, customer Q&A, handle return, refund, resend, etc.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )

    return worker_task


def create_ec_marketing_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa marketing chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "MECA Marketing Chatter Task"), None)

    if not chatter_task:
        task_schedule = TaskSchedule(
                repeat_type=Repeat_Types.BY_DAYS,
                repeat_number=1,
                repeat_unit="day",
                start_date_time="2025-03-31 23:59:59:000",
                end_date_time="2035-12-31 23:59:59:000",
                time_out=120                # seconds.
            )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        chatter_task = ManagedTask(
            id=task_id,
            name="MECA Marketing Chatter Task",
            description="chat with human user about anything related to e-commerce marketing work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )

    return chatter_task

def create_ec_marketing_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa marketing"), None)
    worker_task = next((task for task in agent_tasks if task.name == "E-Commerce Marketing Work"), None)

    if not worker_task:
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
        worker_task = ManagedTask(
            id=task_id,
            name="E-Commerce Marketing Work",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
    return worker_task

def create_ec_procurement_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecan.ai search parts and components web site"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "eCan.ai Procurement Chatter Task"), None)
    print("ec_procurement chatter skill name:", chatter_skill.name)
    print("ec_procurement chatter skill:", chatter_skill)
    if not chatter_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 01:00:00:000",
            end_date_time="2035-12-31 01:30:00:000",
            time_out=1800                # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        chatter_task = ManagedTask(
            id=task_id,
            name="eCan.ai Procurement Chatter Task",
            description="chat with human user about anything related to e-commerce procurement work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="interaction",
            schedule=task_schedule
        )

    return chatter_task

def create_ec_procurement_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if "search parts" in sk.name and "chatter" not in sk.name), None)
    worker_task = next((task for task in agent_tasks if task.name == "E-Commerce Part Procurement Task"), None)

    if not worker_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 01:00:00:000",
            end_date_time="2035-12-31 01:30:00:000",
            time_out=1800  # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        worker_task = ManagedTask(
            id=task_id,
            name="E-Commerce Part Procurement Task",
            description="Help sourcing products/parts for product development",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
    return worker_task

def create_ec_rpa_operator_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa operator run RPA"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "ECBot RPA Operator Chatter Task"), None)

    if not chatter_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        chatter_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Operator Chatter Task",
            description="chat with human user about anything related to ECBOT RPA work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return chatter_task

def create_ec_rpa_operator_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if "ecbot rpa operator run RPA" in sk.name), None)
    worker_task = next((task for task in agent_tasks if task.name == "ECBot RPA operates daily routine task"), None)

    if not worker_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot RPA operates daily routine task",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )

    return worker_task


def create_ec_rpa_supervisor_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa supervisor task scheduling"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "ECBot RPA Operator Chatter Task"), None)

    if not chatter_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        chatter_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Operator Chatter Task",
            description="chat with human user about anything related to ECBOT RPA work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return chatter_task

def create_ec_rpa_supervisor_daily_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    schedule_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor task scheduling"), None)
    daily_task = next((task for task in agent_tasks if task.name == "ECBot RPA Supervise Daily Routine Task"), None)

    if not daily_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 03:00:00:000",
            end_date_time="2035-12-31 23:59:59:000",
            time_out=120  # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        daily_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Supervise Daily Routine Task",
            description="Do any routine like fetch todays work schedule, prepare operators team and dispatch work to the operators to do.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=schedule_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )

    return daily_task

def create_ec_rpa_supervisor_on_request_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    serve_request_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor serve requests"), None)
    on_request_task = next((task for task in agent_tasks if task.name == "ECBot RPA Supervisor Service Task"), None)

    if not on_request_task:
        non_schedule = TaskSchedule(
            repeat_type=Repeat_Types.NONE,
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
        on_request_task = ManagedTask(
            id=task_id,
            name="ECBot RPA Supervisor Service Task",
            description="Serve RPA operators in case they request human in loop or work reports",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=serve_request_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=non_schedule
        )

    return on_request_task


def create_ec_sales_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales internal chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "MECA Sales Chatter Task"), None)

    if not chatter_task:
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
        chatter_task = ManagedTask(
            id=task_id,
            name="MECA Sales Chatter Task",
            description="chat with human user about anything related to e-commerce sales work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return chatter_task

def create_ec_sales_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales"), None)
    worker_task = next((task for task in agent_tasks if task.name == "ECBot Sales"), None)

    if not worker_task:
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
        worker_task = ManagedTask(
            id=task_id,
            name="ECBot Sales",
            description="Help fix errors/failures during e-commerce RPA run",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
    return worker_task




def create_ec_self_tester_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecan.ai self test"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "eCan.ai Self Test Chatter Task"), None)

    if not chatter_task:
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
        chatter_task = ManagedTask(
            id=task_id,
            name="eCan.ai Self Test Chatter Task",
            description="chat with human user about anything related to eCan.ai self test work.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=chatter_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return chatter_task

def create_ec_self_tester_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "eCan.ai self test"), None)
    worker_task = next((task for task in agent_tasks if task.name == "eCan.ai self test"), None)

    if not worker_task:
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
        worker_task = ManagedTask(
            id=task_id,
            name="eCan.ai Self Test",
            description="eCan.ai app software self test",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
    return worker_task



def create_agent_tasks(main_win):
    try:
        # first try to obtain all agents from the cloud, if that fails or there are no agents
        # then build the agents locally
        all_agent_tasks = load_agent_tasks_from_cloud(main_win)
        logger.info("agent tasks from cloud:", all_agent_tasks)
        if not all_agent_tasks:
            # for now just build a few agents.
            all_agent_tasks.append(create_my_twin_chat_task(main_win))
            all_agent_tasks.append(create_ec_helper_chat_task(main_win))
            all_agent_tasks.append(create_ec_helper_work_task(main_win))
            # all_agent_tasks.append(create_ec_customer_support_chat_task(main_win))
            # all_agent_tasks.append(create_ec_customer_support_work_task(main_win))
            all_agent_tasks.append(create_ec_procurement_chat_task(main_win))
            all_agent_tasks.append(create_ec_procurement_work_task(main_win))
            all_agent_tasks.append(create_ec_rpa_operator_chat_task(main_win))
            all_agent_tasks.append(create_ec_rpa_operator_work_task(main_win))
            all_agent_tasks.append(create_ec_rpa_supervisor_chat_task(main_win))
            all_agent_tasks.append(create_ec_rpa_supervisor_daily_task(main_win))
            all_agent_tasks.append(create_ec_rpa_supervisor_on_request_task(main_win))
            all_agent_tasks.append(create_ec_self_tester_chat_task(main_win))
            all_agent_tasks.append(create_ec_self_tester_work_task(main_win))
            # all_agent_tasks.append(create_ec_sales_chat_task(main_win))
            # all_agent_tasks.append(create_ec_sales_work_task(main_win))

        return all_agent_tasks

    except Exception as e:
        logger.error(f"Error in get agent tasks: {e} {traceback.format_exc()}")
        return []






