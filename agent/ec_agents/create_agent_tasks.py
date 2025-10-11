import traceback
import typing
import uuid
import asyncio
from agent.ec_agents.agent_utils import load_agent_tasks_from_cloud
from agent.ec_skills.search_parts.search_parts_chatter_skill import chat_or_work
from agent.tasks import TaskStatus, TaskState

from agent.tasks import ManagedTask, TaskSchedule
from agent.tasks import Repeat_Types

from utils.logger_helper import logger_helper as logger
from agent.ec_agents.create_dev_task import create_skill_dev_task
if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow


def create_my_twin_chat_task(mainwin: 'MainWindow'):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    if agent_skills:
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for my digital twin"), None)
    else:
        chatter_skill = None

    if agent_tasks:
        logger.trace("agent_tasks: ", agent_tasks)
        chatter_task = next((task for task in agent_tasks if task.name == "chat:Human Chatter Task"), None)
    else:
        chatter_task = None

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
            name="chat:Human Chatter Relay Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)

    return chatter_task


def create_ec_helper_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks
    if agent_skills:
        chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa helper"), None)
    else:
        chatter_skill = None

    if agent_tasks:
        logger.trace("agent_tasks: ", agent_tasks)
        chatter_task = next((task for task in agent_tasks if task.name == "chat:ECBot RPA Helper Chatter Task"), None)
    else:
        chatter_task = None

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
            name="chat:ECBot RPA Helper Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_helper_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa helper"), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:ECBot RPA Helper Task"), None)

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
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task


def create_ec_customer_support_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa customer support internal chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:ECBot RPA Customer Support Internal Chatter Task"), None)

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
            name="chat:ECBot RPA Customer Support Internal Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_customer_support_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa customer support"), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:eCan.ai After Sales Customer Support Work"), None)

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
            name="work:eCan.ai After Sales Customer Support Work",
            description="eCan.ai After Sales Support Work like shipping prep, customer Q&A, handle return, refund, resend, etc.",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="schedule",
            schedule=task_schedule
        )
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task


def create_ec_marketing_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa marketing chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:eCan.ai Marketing Chatter Task"), None)

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
            name="chat:eCan.ai Marketing Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_marketing_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa marketing"), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:E-Commerce Marketing Work"), None)

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
            name="work:E-Commerce Marketing Work",
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
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task

def create_ec_procurement_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "search_digikey_chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:eCan.ai Procurement Chatter Task"), None)
    logger.debug("ec_procurement chatter skill name:", chatter_skill.name if chatter_skill else "None")
    logger.debug("ec_procurement chatter skill:", chatter_skill)
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
            name="chat:eCan.ai Procurement Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_procurement_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if "search parts" in sk.name and "chatter" not in sk.name), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:E-Commerce Part Procurement Task"), None)

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
            name="work:E-Commerce Part Procurement Task",
            description="Help sourcing products/parts for product development",
            status=status,  # or whatever default status you need
            sessionId=session_id,
            skill=worker_skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger="message",
            schedule=task_schedule
        )
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task

def create_ec_rpa_operator_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa operator run RPA"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:ECBot RPA Operator Chatter Task"), None)

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
            name="chat:ECBot RPA Operator Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_rpa_operator_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if "ecbot rpa operator run RPA" in sk.name), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:ECBot RPA operates daily routine task"), None)

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
            name="work:ECBot RPA operates daily routine task",
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
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task


def create_ec_rpa_supervisor_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecbot rpa supervisor task scheduling"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:eCan.ai RPA Operator Chatter Task"), None)

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
            name="chat:eCan.ai RPA Operator Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_rpa_supervisor_daily_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    schedule_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor task scheduling"), None)
    daily_task = next((task for task in agent_tasks if task.name == "work:eCan.ai RPA Supervise Daily Routine Task"), None)

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
            name="work:eCan.ai RPA Supervise Daily Routine Task",
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
        logger.info("Created daily_task task: ", daily_task.name, daily_task.id, daily_task.queue)
    return daily_task

def create_ec_rpa_supervisor_on_request_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    serve_request_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa supervisor serve requests"), None)
    on_request_task = next((task for task in agent_tasks if task.name == "work:eCan.ai RPA Supervisor Service Task"), None)

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
            name="work:eCan.ai RPA Supervisor Service Task",
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
        logger.info("Created on_request_task task: ", on_request_task.name, on_request_task.id, on_request_task.queue)
    return on_request_task


def create_ec_sales_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales internal chatter"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:eCan.ai Sales Chatter Task"), None)

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
            name="chat:eCan.ai Sales Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_sales_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "ecbot rpa sales"), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:ECBot Sales"), None)

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
            name="work:ECBot Sales",
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
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task




def create_ec_self_tester_chat_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    chatter_skill = next((sk for sk in agent_skills if sk.name == "chatter for ecan.ai self test"), None)
    chatter_task = next((task for task in agent_tasks if task.name == "chat:eCan.ai Self Test Chatter Task"), None)

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
            name="chat:eCan.ai Self Test Chatter Task",
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
        logger.info("Created chat task: ", chatter_task.name, chatter_task.id, chatter_task.queue)
    return chatter_task

def create_ec_self_tester_work_task(mainwin):
    agent_skills = mainwin.agent_skills
    agent_tasks = mainwin.agent_tasks

    worker_skill = next((sk for sk in agent_skills if sk.name == "eCan.ai self test"), None)
    worker_task = next((task for task in agent_tasks if task.name == "work:eCan.ai self test"), None)

    if not worker_task:
        task_schedule = TaskSchedule(
            repeat_type=Repeat_Types.BY_DAYS,
            repeat_number=1,
            repeat_unit="day",
            start_date_time="2025-03-31 01:59:59:000",
            end_date_time="2035-12-31 01:59:59:000",
            time_out=120  # seconds.
        )

        task_id = str(uuid.uuid4())
        session_id = ""
        resume_from = ""
        state = {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        worker_task = ManagedTask(
            id=task_id,
            name="work:eCan.ai Self Test",
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
        logger.info("Created worker task: ", worker_task.name, worker_task.id, worker_task.queue)
    return worker_task



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
                repeat_type=getattr(Repeat_Types, schedule_data.get('repeat_type', 'NONE'), Repeat_Types.NONE),
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
        # logger.info("[build_agent_tasks] Step 4: Building local code agent tasks...")
        # try:
        #     local_agent_tasks = await _build_local_agent_tasks_async(main_win)
        #     logger.info(f"[build_agent_tasks] ✅ Built {len(local_agent_tasks or [])} local code agent tasks")
        # except Exception as e:
        #     logger.error(f"[build_agent_tasks] ❌ Local build failed: {e}")
        #     local_agent_tasks = []

        # Step 5: Merge all agent task data
        logger.info("[build_agent_tasks] Step 5: Merging all agent tasks...")
        all_agent_tasks = []

        # First add database/cloud agent tasks
        all_agent_tasks.extend(final_db_agent_tasks)

        # Then add locally built agent tasks from code
        if local_agent_tasks:
            all_agent_tasks.extend(local_agent_tasks)

        # Filter out None objects
        all_agent_tasks = [agent_task for agent_task in all_agent_tasks if agent_task is not None]

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






