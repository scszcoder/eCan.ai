from agent.ec_skill import *
from agent.ec_agents.ec_marketing_agent import *
from agent.ec_agents.ec_sales_agent import *
from agent.ec_agents.ec_helper_agent import *
from agent.ec_agents.ec_rpa_supervisor_agent import *
from agent.ec_agents.ec_rpa_operator_agent import *
from agent.ec_agents.my_twin_agent import *
from agent.ec_agents.ec_procurement_agent import *
from agent.ec_agents.ec_marketing_agent import *
from agent.ec_agents.agent_utils import load_agent_tasks_from_cloud
from utils.logger_helper import logger_helper as logger



def create_my_twin_chat_task(main_win):
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


def create_ec_helper_chat_task(main_win):
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

def create_ec_helper_work_task(main_win):
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


def create_ec_customer_support_chat_task(main_win):
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

def create_ec_customer_support_work_task(main_win):
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
        name="ECBot RPA After Sales Support Work like shipping prep, customer Q&A, handle return, refund, resend, etc.",
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


def create_ec_marketing_chat_task(main_win):
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

def create_ec_marketing_work_task(main_win):
    task_id = str(uuid.uuid4())
    session_id = ""
    resume_from = ""
    state = {"top": "ready"}
    status = TaskStatus(state=TaskState.SUBMITTED)
    worker_task = ManagedTask(
        id=task_id,
        name="MECA Marketing Director",
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

def create_ec_procurement_chat_task(main_win):

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
        name="MECA Procurement Chatter Task",
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

def create_ec_procurement_work_task(main_win):
    task_id = str(uuid.uuid4())
    session_id = ""
    resume_from = ""
    state = {"top": "ready"}
    status = TaskStatus(state=TaskState.SUBMITTED)
    worker_task = ManagedTask(
        id=task_id,
        name="ECBot Part Procurement Task",
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

def create_ec_rpa_operator_chat_task(main_win):
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

def create_ec_rpa_operator_work_task(main_win):
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


def create_ec_rpa_supervisor_chat_task(main_win):
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

def create_ec_rpa_supervisor_daily_task(main_win):
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

def create_ec_rpa_supervisor_on_request_task(main_win):
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


def create_ec_sales_chat_task(main_win):
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

def create_ec_sales_work_task(main_win):
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

def create_agent_tasks(main_win):
    try:
        # first try to obtain all agents from the cloud, if that fails or there are no agents
        # then build the agents locally
        all_agent_tasks = load_agent_tasks_from_cloud(main_win)
        print("agent tasks from cloud:", all_agent_tasks)
        if not all_agent_tasks:
            # for now just build a few agents.
            all_agent_tasks.append(create_my_twin_chat_task(main_win))
            all_agent_tasks.append(create_ec_helper_chat_task(main_win))
            all_agent_tasks.append(create_ec_helper_work_task(main_win))
            all_agent_tasks.append(create_ec_customer_support_chat_task(main_win))
            all_agent_tasks.append(create_ec_customer_support_work_task(main_win))
            all_agent_tasks.append(create_ec_procurement_chat_task(main_win))
            all_agent_tasks.append(create_ec_procurement_work_task(main_win))
            all_agent_tasks.append(create_ec_rpa_operator_chat_task(main_win))
            all_agent_tasks.append(create_ec_rpa_operator_work_task(main_win))
            all_agent_tasks.append(create_ec_rpa_supervisor_chat_task(main_win))
            all_agent_tasks.append(create_ec_rpa_supervisor_daily_task(main_win))
            all_agent_tasks.append(create_ec_rpa_supervisor_on_request_task(main_win))
            all_agent_tasks.append(create_ec_sales_chat_task(main_win))
            all_agent_tasks.append(create_ec_sales_work_task(main_win))

        return all_agent_tasks

    except Exception as e:
        logger.error(f"Error in get agent tasks: {e} {traceback.format_exc()}")
        return []






