from skill.steps.step_base import StepBase
from enum import Enum


class StepCheckCondition(StepBase):
    def __init__(self, stepN, condition, ifelse, ifend):
        super().__init__(stepN)

        self.type = "Check Condition"
        self.condition = condition
        self.if_else = ifelse
        self.if_end = ifend
