from gui.skill.steps.step_base import StepBase
from enum import Enum


class StepTextToNumber(StepBase):
    TYPE_KEY = "Text To Number"

    def __init__(self, stepN=0, invar=None, outvar=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.intext = invar
        self.numvar = outvar
