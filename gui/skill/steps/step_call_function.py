from skill.steps.step_base import StepBase
from basicSkill import STEP_GAP
from enum import Enum


class StepCallFunction(StepBase):
    def __init__(self, stepN, fname, fargs, output):
        super().__init__(stepN)

        self.type = "Call Function"
        self.fname = fname
        self.fargs = fargs
        self.return_to = stepN + STEP_GAP
        self.output = output
