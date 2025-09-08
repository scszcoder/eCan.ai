from agent.ec_skills.flowgram2langgraph import flowgram2langgraph
from utils.logger_helper import get_traceback

def setup_dev_skill(mainwin, skill):
    dev_run_tesk = next((task for task in mainwin.agent_tasks if "run task for skill under development" in task.name.lower()), None)
    tester_agent = next((ag for ag in mainwin.agents if "test" in ag.card.name.lower()), None)
    skill_under_dev = flowgram2langgraph(skill)
    dev_run_tesk.skill.set_work_flow(skill_under_dev)
    return tester_agent

def run_dev_skill(mainwin, skill):
    tester_agent = setup_dev_skill(mainwin, skill)
    tester_agent.lauch_dev_run_task()