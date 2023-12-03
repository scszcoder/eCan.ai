from skill.steps.step_base import StepBase
from enum import Enum


class StepUseSkill(StepBase):
    def __init__(self, stepN, skname, skpath, skargs, output):
        super().__init__(stepN)

        self.type = "Use Skill"
        self.skill_name = skname
        self.skill_path = skpath
        self.skill_args = skargs
        self.output = output
