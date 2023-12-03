from skill.steps.step_base import StepBase
from enum import Enum


class StepEndException(StepBase):
    def __init__(self, stepN, cause, cdata):
        super().__init__(stepN)

        self.type = "End Exception"
        self.cause = cause
        self.cdata = cdata
