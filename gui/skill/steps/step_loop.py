from skill.steps.step_base import StepBase
from enum import Enum


class StepLoop(StepBase):
    def __init__(self, stepN, condition, count, end, lc_name):
        super().__init__(stepN)

        self.type = "Repeat"
        self.lc_name = lc_name
        self.until = condition
        self.count = count
        self.end = end
