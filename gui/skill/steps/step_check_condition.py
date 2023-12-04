from skill.steps.step_base import StepBase
from enum import Enum


class StepCheckCondition(StepBase):
    TYPE_KEY = "Check Condition"

    def __init__(self, stepN=0, condition=None, ifelse=None, ifend=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.condition = condition
        self.if_else = ifelse
        self.if_end = ifend
