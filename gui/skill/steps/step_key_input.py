from skill.steps.step_base import StepBase
from enum import Enum


class StepKeyInput(StepBase):
    TYPE_KEY = "Key Input"

    def __init__(self, stepN=0, action=None, saverb=None, val=None, loc=None, wait_after=None):
        super().__init__(stepN)

        self.type = self.TYPE_KEY
        self.action = action
        self.action_value = val
        self.save_rb = saverb
        self.location = loc
        self.wait_after = wait_after
