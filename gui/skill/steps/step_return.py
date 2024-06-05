from gui.skill.steps.step_base import StepBase
from enum import Enum


class StepReturn(StepBase):
    TYPE_KEY = "Return"

    def __init__(self, stepN=0, output=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.val_var_name = output

