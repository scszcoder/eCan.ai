from skill.steps.step_base import StepBase
from enum import Enum


class StepExceptionHandler(StepBase):
    TYPE_KEY = "Exception Handler"

    def __init__(self, stepN=0, cause=None, cdata=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.cause = cause
        self.cdata = cdata
