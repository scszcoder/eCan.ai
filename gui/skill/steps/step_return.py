from skill.steps.step_base import StepBase
from enum import Enum


class StepReturn(StepBase):
    def __init__(self, stepN, output):
        super().__init__(stepN)

        self.type = "Return"
        self.val_var_name = output

