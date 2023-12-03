from skill.steps.step_base import StepBase
from enum import Enum


class StepKeyInput(StepBase):
    def __init__(self, stepN, action, saverb, val, loc, wait_after):
        super().__init__(stepN)

        self.type = "Key Input"
        self.action = action
        self.action_value = val
        self.save_rb = saverb
        self.location = loc
        self.wait_after = wait_after
