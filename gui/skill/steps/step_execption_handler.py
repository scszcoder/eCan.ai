from skill.steps.step_base import StepBase
from enum import Enum


class StepExceptionHandler(StepBase):
    def __init__(self, stepN, cause, cdata):
        super().__init__(stepN)

        self.type = "Exception Handler"
        self.cause = cause
        self.cdata = cdata
