from skill.steps.step_base import StepBase
from enum import Enum


class StepUseSkill(StepBase):
    TYPE_KEY = "Use Skill"

    def __init__(self, stepN=0, skname=None, skpath=None, skargs=None, output=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.skill_name = skname
        self.skill_path = skpath
        self.skill_args = skargs
        self.output = output
